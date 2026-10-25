"""Ленты официальных оповещений: источники по регионам, разбор постов, классификация и запуск тревог.

Откуда берём оповещения, почему именно оттуда и какие есть ограничения: docs/ALERTS.md.
Сами тревоги создаёт и завершает modules/safety/service.py, здесь только решаем, когда и в каких домах.
"""

import asyncio
import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Literal

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.core.config import Settings, get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.modules.misc_models import Alert
from domovoy.modules.safety import service
from domovoy.modules.safety.feed_models import SOURCE_TYPES, AlertSource
from domovoy.modules.safety.regions import REGIONS, mchs_rss_url, normalize_code
from domovoy.modules.users.models import House

log = structlog.get_logger(__name__)

USER_AGENT = "DomovoyKuzya/1.0"
TIMEOUT_SECONDS = 15.0
# Сколько источников читаем одновременно за один проход
FETCH_CONCURRENCY = 8
# Ленты сайтов МЧС обновляются редко (прогноз раз в сутки), их опрашиваем не чаще раза в 5 минут
RSS_MIN_INTERVAL = timedelta(minutes=5)
# Пост старше этого срока тревогу не запускает, даже если лента отдала его впервые: защита от повтора старых оповещений
MAX_POST_AGE = timedelta(hours=2)
# При первом опросе нового источника берём только совсем свежие посты, историю не проигрываем
FIRST_RUN_WINDOW = timedelta(minutes=30)
MESSAGE_CHARS = 300
SOURCE_PREFIX = "feed:"
VK_API_URL = "https://api.vk.com/method/wall.get"
VK_API_VERSION = "5.199"
VK_POSTS = 20
YANDEX_NS = "{http://news.yandex.ru}"

AlertEvent = Literal["start", "end"]
AlertKind = Literal["drone", "air", "other"]

# Публичные каналы пилотного региона, проверенные запросом к t.me/s/<имя> (см. docs/ALERTS.md)
PILOT_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("RU-ULY", "telegram_web", "mchs_ulyanovsk", "МЧС Ульяновской области (Telegram)"),
    ("RU-ULY", "telegram_web", "Russkih_Aleksey", "Алексей Русских, губернатор Ульяновской области (Telegram)"),
)


class FeedError(Exception):
    """Источник не удалось прочитать; текст попадает в last_error источника."""


@dataclass(frozen=True)
class Post:
    post_id: str
    text: str
    published_at: datetime | None
    url: str


@dataclass(frozen=True)
class Verdict:
    event: AlertEvent | None
    kind: AlertKind


# ----- классификатор -------------------------------------------------------------------------------

# Тексты приводим к нижнему регистру без «ё», поэтому в шаблонах только «е»
FORECAST_RE = re.compile(r"оперативн\w* (ежедневн\w* )?прогноз|прогноз (возникновения )?(чс|чрезвычайн)")
DRILL_RE = re.compile(r"\b(учени[яйе]|учебн\w+|тренировк\w*|тренировочн\w+)\b|проверк\w* (систем\w* )?оповещени")
START_RES = tuple(
    re.compile(p)
    for p in (
        r"(объявлен|введен|установлен|действует|вводится)\w* (режим\w* )?[«\"']?беспилотн\w* опасност",
        r"внимание[!.,:]* [«\"']?беспилотн\w* опасност",
        r"^[^а-я]*(режим\w* )?[«\"']?беспилотн\w* опасност",
        r"ракетн\w* опасност",
        r"воздушн\w* тревог",
        r"внимание всем",
        r"(угроза|опасность) (атак\w* )?(бпла|беспилотн)",
    )
)
END_RES = tuple(
    re.compile(p)
    for p in (
        r"\bотбой\b",
        r"опасность миновала",
        r"угроза[^.!\n]{0,60}миновала",
        r"режим\w*[^.!\n]{0,60}(снят|отменен|завершен|прекращен)",
        r"(снят|отменен|завершен|прекращен)\w*[^.!\n]{0,40}режим",
        r"отмена (режима )?[«\"']?(беспилотн|ракетн|воздушн)",
    )
)
KIND_DRONE_RE = re.compile(r"беспилотн|бпла|дрон")
KIND_AIR_RE = re.compile(r"воздушн\w* тревог|ракетн\w* опасност")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().replace("ё", "е")).strip()


def _kind(low: str) -> AlertKind:
    if KIND_DRONE_RE.search(low):
        return "drone"
    if KIND_AIR_RE.search(low):
        return "air"
    return "other"


def _first_match(patterns: Iterable[re.Pattern[str]], low: str) -> int | None:
    positions = [m.start() for p in patterns if (m := p.search(low))]
    return min(positions) if positions else None


def classify(text: str) -> Verdict:
    """Что это за пост: начало тревоги, отбой или просто новость.

    Побеждает формулировка, которая встретилась раньше: в «Объявлен режим... Отбой сообщим дополнительно»
    это начало, в «Отбой беспилотной опасности» - отбой. Учения, тренировки и прогнозы ЧС не тревога.
    """
    low = _norm(text)
    kind = _kind(low)
    if not low or FORECAST_RE.search(low) or DRILL_RE.search(low):
        return Verdict(None, kind)
    start, end = _first_match(START_RES, low), _first_match(END_RES, low)
    # Одинокое «отбой» без слов про БПЛА или ракеты считаем отбоем, только если пост с него начинается
    end_is_alert = kind != "other" or re.match(r"^[^а-я]*отбой", low) is not None
    if end is not None and end_is_alert and (start is None or end <= start):
        return Verdict("end", kind)
    if start is not None:
        return Verdict("start", kind)
    return Verdict(None, kind)


# ----- разбор лент ---------------------------------------------------------------------------------


def strip_html(raw: str) -> str:
    """HTML из RSS в обычный текст: переносы вместо абзацев, без тегов и сущностей."""
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", raw)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _parse_rfc822(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value.strip())
    except (TypeError, ValueError, IndexError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def parse_rss(xml_text: str) -> list[Post]:
    """RSS 2.0 региональных сайтов МЧС: title, link, pubDate и полный текст в yandex:full-text."""
    try:
        root = ET.fromstring(xml_text)  # noqa: S314  ленты только из белого списка официальных сайтов
    except ET.ParseError as exc:
        raise FeedError(f"RSS не разобрать: {exc}") from exc
    posts: list[Post] = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        guid = (item.findtext("guid") or "").strip()
        post_id = link or guid
        if not post_id:
            continue
        title = (item.findtext("title") or "").strip()
        body = strip_html(item.findtext(f"{YANDEX_NS}full-text") or item.findtext("description") or "")
        posts.append(
            Post(
                post_id=post_id,
                text=f"{title}\n{body}".strip(),
                published_at=_parse_rfc822(item.findtext("pubDate")),
                url=link or guid,
            )
        )
    return posts


class _TelegramPage(HTMLParser):
    """Собирает посты со страницы t.me/s/<канал>: data-post, текст, время публикации и ссылку."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: list[dict[str, str]] = []
        self._post: dict[str, str] | None = None
        self._depth = 0
        self._text_depth: int | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: v or "" for k, v in attrs}
        classes = attr.get("class", "").split()
        if tag == "div":
            if "tgme_widget_message" in classes and attr.get("data-post"):
                self._close_post()
                self._post = {"id": attr["data-post"], "text": "", "url": "", "time": ""}
                self._depth = 1
                return
            if self._post is not None:
                self._depth += 1
                # js-message_text - текст самого поста; у цитаты в ответе класс js-message_reply_text
                if "js-message_text" in classes and self._text_depth is None:
                    self._text_depth, self._chunks = self._depth, []
            return
        if self._post is None:
            return
        if tag == "br" and self._text_depth is not None:
            self._chunks.append("\n")
        elif tag == "a" and "tgme_widget_message_date" in classes:
            self._post["url"] = attr.get("href", "")
        elif tag == "time" and attr.get("datetime"):
            self._post["time"] = attr["datetime"]

    def handle_endtag(self, tag: str) -> None:
        if self._post is None or tag != "div":
            return
        if self._text_depth == self._depth:
            self._post["text"] = "".join(self._chunks)
            self._text_depth = None
        self._depth -= 1
        if self._depth == 0:
            self._close_post()

    def handle_data(self, data: str) -> None:
        if self._text_depth is not None:
            self._chunks.append(data)

    def close(self) -> None:
        super().close()
        self._close_post()

    def _close_post(self) -> None:
        if self._post is not None:
            self.posts.append(self._post)
            self._post = None


def parse_telegram_html(page: str, channel: str) -> list[Post]:
    """Публичная веб-версия канала (https://t.me/s/<канал>) без API и ключей."""
    parser = _TelegramPage()
    parser.feed(page)
    parser.close()
    posts: list[Post] = []
    for raw in parser.posts:
        _, _, num = raw["id"].rpartition("/")
        if not num.isdigit():
            continue
        text = re.sub(r"[ \t\xa0]+", " ", raw["text"])
        text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
        posts.append(
            Post(
                post_id=num,
                text=text,
                published_at=_parse_iso(raw["time"]),
                url=raw["url"] or f"https://t.me/{channel}/{num}",
            )
        )
    return posts


def parse_vk_wall(data: dict[str, Any]) -> list[Post]:
    """Ответ wall.get: response.items с id, owner_id, date (unix) и text."""
    if "error" in data:
        raise FeedError(str((data.get("error") or {}).get("error_msg") or "ошибка VK API"))
    posts: list[Post] = []
    for item in (data.get("response") or {}).get("items") or []:
        try:
            post_id, owner = int(item["id"]), int(item["owner_id"])
        except (KeyError, TypeError, ValueError):
            continue
        stamp = item.get("date")
        posts.append(
            Post(
                post_id=str(post_id),
                text=str(item.get("text") or ""),
                published_at=datetime.fromtimestamp(int(stamp), UTC) if stamp else None,
                url=f"https://vk.com/wall{owner}_{post_id}",
            )
        )
    return posts


async def _get_text(http: httpx.AsyncClient, url: str) -> str:
    try:
        resp = await http.get(url)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise FeedError(f"{type(exc).__name__}: {exc}") from exc
    return resp.text


async def fetch_new_posts(http: httpx.AsyncClient, source: AlertSource) -> list[Post]:
    """Все посты, какие отдаёт источник (обычно 10-20 последних). Какие из них новые, решает select_new."""
    if source.type == "mchs_rss":
        return parse_rss(await _get_text(http, source.ref))
    if source.type == "telegram_web":
        return parse_telegram_html(await _get_text(http, f"https://t.me/s/{source.ref}"), source.ref)
    if source.type == "vk_wall":
        token = get_settings().vk_service_token.get_secret_value()
        if not token:
            raise FeedError("VK_SERVICE_TOKEN не задан, источник не опрашивается")
        ref = source.ref.strip()
        params = {"count": str(VK_POSTS), "access_token": token, "v": VK_API_VERSION}
        params["owner_id" if re.fullmatch(r"-?\d+", ref) else "domain"] = ref
        try:
            resp = await http.get(VK_API_URL, params=params)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise FeedError(f"{type(exc).__name__}: {exc}") from exc
        return parse_vk_wall(resp.json())
    # max_channel: посты каналов MAX приходят боту сами (ingest_channel_post), опрашивать нечего
    return []


# ----- отбор новых постов --------------------------------------------------------------------------

_EPOCH = datetime.min.replace(tzinfo=UTC)


def _order_key(post: Post) -> tuple[datetime, int]:
    return (post.published_at or _EPOCH, int(post.post_id) if post.post_id.isdigit() else 0)


def newest_post_id(posts: Sequence[Post]) -> str | None:
    return max(posts, key=_order_key).post_id if posts else None


def select_new(posts: Sequence[Post], last_post_id: str | None, now: datetime | None = None) -> list[Post]:
    """Какие посты обрабатывать: новее последнего известного и не старше MAX_POST_AGE, от старых к новым.

    У Telegram, VK и MAX номера постов растут, сравниваем числа. У RSS id - ссылка, поэтому берём
    всё, что в ленте идёт после последней известной; если её уже вытеснило, спасает ограничение по возрасту.
    """
    moment = now or datetime.now(UTC)
    ordered = sorted(posts, key=_order_key)
    if last_post_id is None:
        window = moment - FIRST_RUN_WINDOW
        return [p for p in ordered if p.published_at is not None and p.published_at >= window]
    if last_post_id.isdigit() and all(p.post_id.isdigit() for p in ordered):
        fresh = [p for p in ordered if int(p.post_id) > int(last_post_id)]
    else:
        ids = [p.post_id for p in ordered]
        fresh = ordered[ids.index(last_post_id) + 1 :] if last_post_id in ids else ordered
    cutoff = moment - MAX_POST_AGE
    return [p for p in fresh if p.published_at is None or p.published_at >= cutoff]


# ----- диспетчер тревог ----------------------------------------------------------------------------


def alert_message(text: str, source_title: str) -> str:
    """Сообщение жителям: начало официального текста и источник."""
    body = re.sub(r"\s+", " ", text).strip()
    if len(body) > MESSAGE_CHARS:
        body = body[:MESSAGE_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:-") + "…"
    return f"{body}\n\nИсточник: {source_title}".strip()


def source_ref(source: AlertSource, post: Post) -> str:
    return f"{SOURCE_PREFIX}{source.type}:{source.ref}:{post.post_id}"[:256]


def houses_to_alert(houses: Iterable[House], active: Iterable[Alert], kind: str) -> list[House]:
    """Дома, где тревогу этого вида ещё надо запустить: без активной своей и без общей (house_id = None)."""
    busy = {a.house_id for a in active if a.active and a.kind == kind}
    if None in busy:
        return []
    return [h for h in houses if h.id not in busy]


async def ingest_post(session: AsyncSession, source: AlertSource, post: Post) -> Verdict:
    """Разобрать пост источника и, если это тревога или отбой, применить к домам региона."""
    verdict = classify(post.text)
    if verdict.event is None:
        return verdict
    log.info(
        "alert_feed.post",
        region=source.region,
        source=f"{source.type}:{source.ref}",
        post_id=post.post_id,
        event=verdict.event,
        kind=verdict.kind,
    )
    if verdict.event == "start":
        await _start_region(session, source, post, verdict.kind)
    else:
        await _end_region(session, source.region)
    return verdict


async def _start_region(session: AsyncSession, source: AlertSource, post: Post, kind: AlertKind) -> None:
    houses = list(await session.scalars(select(House).where(House.region == source.region)))
    if not houses:
        return
    active = list(
        await session.scalars(
            select(Alert).where(
                Alert.active.is_(True),
                Alert.kind == kind,
                Alert.house_id.in_([h.id for h in houses]) | Alert.house_id.is_(None),
            )
        )
    )
    message = alert_message(post.text, source.title or source.ref)
    for house in houses_to_alert(houses, active, kind):
        alert = await service.start_alert(session, house, service.AlertIn(kind=kind, message=message))
        alert.region, alert.source = source.region, source_ref(source, post)
        await session.commit()


async def _feed_alerts(
    session: AsyncSession, region: str | None, created_before: datetime | None
) -> list[tuple[Alert, House]]:
    """Активные тревоги из лент вместе с домами; по желанию только региона или только старше created_before."""
    stmt = (
        select(Alert, House)
        .join(House, House.id == Alert.house_id)
        .where(Alert.active.is_(True), Alert.source.like(f"{SOURCE_PREFIX}%"))
        .order_by(Alert.id)
    )
    if region is not None:
        stmt = stmt.where(House.region == region)
    if created_before is not None:
        stmt = stmt.where(Alert.created_at < created_before)
    return [(alert, house) for alert, house in (await session.execute(stmt)).all()]


async def _end_region(session: AsyncSession, region: str) -> None:
    """Официальный отбой: закрываем тревоги региона, которые пришли из лент (ручные остаются администратору)."""
    for alert, house in await _feed_alerts(session, region, None):
        await service.end_alert(session, house, alert.id)


async def expire_stale_alerts(session: AsyncSession, now: datetime | None = None) -> int:
    """Страховка: тревога из ленты без официального отбоя снимается через ALERT_FEED_MAX_HOURS."""
    hours = get_settings().alert_feed_max_hours
    cutoff = (now or datetime.now(UTC)) - timedelta(hours=hours)
    stale = await _feed_alerts(session, None, cutoff)
    for alert, house in stale:
        log.info("alert_feed.expired", alert_id=alert.id, house_id=house.id, hours=hours)
        if house.max_chat_id:
            await bus.bot_send(
                chat_id=house.max_chat_id,
                text=(
                    f"⏱ Прошло {hours} ч с начала оповещения, официального отбоя в источниках не было. "
                    "Снимаю тревогу автоматически. Следите за сообщениями МЧС и администрации региона."
                ),
            )
        await service.end_alert(session, house, alert.id)
    return len(stale)


# ----- источники -----------------------------------------------------------------------------------


async def ensure_default_sources() -> int:
    """Ленты сайтов МЧС для всех регионов справочника и проверенные каналы пилота. Идемпотентно."""
    async with get_sessionmaker()() as session:
        existing = {(s.type, s.ref) for s in await session.scalars(select(AlertSource))}
        added = 0
        for code, region in REGIONS.items():
            url = mchs_rss_url(code)
            if ("mchs_rss", url) not in existing:
                title = f"ГУ МЧС России: {region.name}, оперативная информация"
                session.add(AlertSource(region=code, type="mchs_rss", ref=url, title=title))
                added += 1
        for code, source_type, ref, title in PILOT_SOURCES:
            if (source_type, ref) not in existing:
                session.add(AlertSource(region=code, type=source_type, ref=ref, title=title))
                added += 1
        await session.commit()
    return added


async def add_source(region: str, source_type: str, ref: str, title: str, enabled: bool = True) -> AlertSource:
    """Добавить или обновить источник (CLI `domovoy add-alert-source`). Ключ уникальности - тип и ref."""
    code = normalize_code(region)
    if code is None:
        raise ValueError("Регион задаётся кодом ISO 3166-2, например RU-ULY")
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"Тип источника: {', '.join(SOURCE_TYPES)}")
    clean_ref = ref.strip().lstrip("@") if source_type == "telegram_web" else ref.strip()
    if not clean_ref:
        raise ValueError("Пустой ref источника")
    if code not in REGIONS:
        log.warning("alert_feed.unknown_region", region=code)
    async with get_sessionmaker()() as session:
        source = await session.scalar(
            select(AlertSource).where(AlertSource.type == source_type, AlertSource.ref == clean_ref)
        )
        if source is None:
            source = AlertSource(type=source_type, ref=clean_ref)
            session.add(source)
        source.region, source.enabled = code, enabled
        source.title = title.strip() or source.title or clean_ref
        await session.commit()
        await session.refresh(source)
        return source


# ----- опрос ---------------------------------------------------------------------------------------


def _is_due(source: AlertSource, now: datetime, settings: Settings) -> bool:
    if source.type == "max_channel":
        return False
    if source.type == "vk_wall" and not settings.vk_service_token.get_secret_value():
        return False
    checked = source.last_checked_at
    return not (source.type == "mchs_rss" and checked is not None and now - checked < RSS_MIN_INTERVAL)


async def _fetch_guarded(http: httpx.AsyncClient, source: AlertSource, sem: asyncio.Semaphore) -> list[Post] | str:
    """Посты источника или текст ошибки: сбой одного источника не трогает остальные."""
    async with sem:
        try:
            return await fetch_new_posts(http, source)
        except FeedError as exc:
            # сеть или чужая разметка: обычное дело для 90 источников, трассировка в логе не нужна
            log.warning("alert_feed.fetch_failed", source=f"{source.type}:{source.ref}", error=str(exc))
            return str(exc)[:500]
        except Exception as exc:
            log.warning("alert_feed.fetch_failed", source=f"{source.type}:{source.ref}", exc_info=True)
            return f"{type(exc).__name__}: {exc}"[:500]


async def _apply_result(session: AsyncSession, source: AlertSource, result: list[Post] | str, now: datetime) -> None:
    source.last_checked_at = now
    if isinstance(result, str):
        source.last_error = result
        await session.commit()
        return
    try:
        for post in select_new(result, source.last_post_id, now):
            await ingest_post(session, source, post)
        newest = newest_post_id(result)
        if newest:
            source.last_post_id = newest
        source.last_error = None
        await session.commit()
    except Exception:
        log.exception("alert_feed.process_failed", source=f"{source.type}:{source.ref}")
        await session.rollback()


async def poll_sources_once(now: datetime | None = None) -> None:
    """Один проход по включённым источникам: читаем параллельно, применяем по очереди."""
    moment = now or datetime.now(UTC)
    settings = get_settings()
    async with get_sessionmaker()() as session:
        sources = list(
            await session.scalars(select(AlertSource).where(AlertSource.enabled.is_(True)).order_by(AlertSource.id))
        )
        due = [s for s in sources if _is_due(s, moment, settings)]
        if not due:
            return
        sem = asyncio.Semaphore(FETCH_CONCURRENCY)
        headers = {"User-Agent": USER_AGENT}
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as http:
            results = await asyncio.gather(*(_fetch_guarded(http, s, sem) for s in due))
        for source, result in zip(due, results, strict=True):
            await _apply_result(session, source, result, moment)


async def ingest_channel_post(message: dict[str, Any]) -> bool:
    """Пост канала MAX, в который Кузю добавили администратором. True, если канал в белом списке источников."""
    recipient = message.get("recipient") or {}
    body = message.get("body") or {}
    chat_id = recipient.get("chat_id")
    text = str(body.get("text") or "").strip()
    if chat_id is None or not text:
        return False
    async with get_sessionmaker()() as session:
        source = await session.scalar(
            select(AlertSource).where(
                AlertSource.type == "max_channel", AlertSource.ref == str(chat_id), AlertSource.enabled.is_(True)
            )
        )
        if source is None:
            return False
        stamp = message.get("timestamp")
        published = datetime.fromtimestamp(int(stamp) / 1000, UTC) if stamp else datetime.now(UTC)
        post = Post(
            post_id=str(body.get("mid") or int(published.timestamp())),
            text=text,
            published_at=published,
            url=str(message.get("url") or ""),
        )
        await ingest_post(session, source, post)
        source.last_post_id, source.last_checked_at, source.last_error = post.post_id, datetime.now(UTC), None
        await session.commit()
    return True


async def run_forever() -> None:
    """Цикл воркера: опрос источников и автоотбой. Выключается ALERT_FEEDS_ENABLED=false."""
    settings = get_settings()
    if not settings.alert_feeds_enabled:
        log.info("alert_feed.disabled")
        return
    added = await ensure_default_sources()
    log.info("alert_feed.started", added_sources=added, interval=settings.alert_feed_interval_seconds)
    while True:
        try:
            await poll_sources_once()
            async with get_sessionmaker()() as session:
                await expire_stale_alerts(session)
        except Exception:
            log.exception("alert_feed.tick_failed")
        await asyncio.sleep(settings.alert_feed_interval_seconds)
