"""Ленты официальных оповещений с базой: запуск и отбой тревог по региону, автоотбой, источники, опрос."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from fakes import FakeBroker, FakeInternet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.modules.misc_models import Alert
from domovoy.modules.safety import feeds
from domovoy.modules.safety.feed_models import AlertSource
from domovoy.modules.safety.service import AlertIn, start_alert
from integration.helpers import Home, make_home, next_id

pytestmark = pytest.mark.integration

START = "Внимание! Объявлен режим беспилотной опасности. Отойдите от окон."
END = "Отбой беспилотной опасности. Режим снят."


def region_code() -> str:
    return f"XX-F{next_id()}"


async def new_source(session: AsyncSession, region: str, **extra: str) -> AlertSource:
    values = {"type": "telegram_web", "ref": f"chan_{region}", "title": "МЧС региона (Telegram)", **extra}
    source = AlertSource(region=region, **values)
    session.add(source)
    await session.commit()
    return source


def post(text: str, post_id: str = "10", minutes_ago: int = 1) -> feeds.Post:
    return feeds.Post(
        post_id=post_id,
        text=text,
        published_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
        url=f"https://t.me/x/{post_id}",
    )


async def active_alerts(_: AsyncSession, home: Home) -> list[Alert]:
    """Активные тревоги дома, прочитанные заново (отдельной сессией, без кэша объектов)."""
    async with get_sessionmaker()() as fresh:
        return list(await fresh.scalars(select(Alert).where(Alert.house_id == home.house.id, Alert.active.is_(True))))


async def source_row(source_id: int) -> AlertSource:
    async with get_sessionmaker()() as fresh:
        row = await fresh.get(AlertSource, source_id)
        assert row is not None
        return row


class TestRegionAlerts:
    async def test_start_once_per_house_then_official_end(self, session: AsyncSession, broker: FakeBroker) -> None:
        region = region_code()
        homes = [await make_home(region=region), await make_home(region=region)]
        outside = await make_home(region=region_code())
        source = await new_source(session, region)

        verdict = await feeds.ingest_post(session, source, post(START))
        assert (verdict.event, verdict.kind) == ("start", "drone")
        for home in homes:
            (alert,) = await active_alerts(session, home)
            assert alert.region == region
            assert alert.source == f"feed:telegram_web:chan_{region}:10"
            assert "Источник: МЧС региона (Telegram)" in alert.message
            assert broker.sent(chat_id=home.chat_id)[0]["text"].startswith("🚨")
        assert await active_alerts(session, outside) == []

        # повтор того же оповещения не плодит вторую тревогу
        await feeds.ingest_post(session, source, post(START, "11"))
        assert all([len(await active_alerts(session, h)) == 1 for h in homes])

        # ручная тревога администратора официальным отбоем не снимается
        async with get_sessionmaker()() as s:
            manual_house = await s.get(type(homes[0].house), homes[0].house.id)
            assert manual_house is not None
            await start_alert(s, manual_house, AlertIn(kind="air"))

        broker.published.clear()
        verdict = await feeds.ingest_post(session, source, post(END, "12"))
        assert verdict.event == "end"
        assert [a.kind for a in await active_alerts(session, homes[0])] == ["air"]
        assert await active_alerts(session, homes[1]) == []
        assert broker.sent(chat_id=homes[1].chat_id)[0]["text"].startswith("✅ Отбой")

    async def test_news_and_empty_region_change_nothing(self, session: AsyncSession, broker: FakeBroker) -> None:
        source = await new_source(session, region_code())
        assert (await feeds.ingest_post(session, source, post("Прогноз погоды на завтра"))).event is None
        # в регионе нет домов: тревогу запускать негде
        assert (await feeds.ingest_post(session, source, post(START))).event == "start"
        assert broker.sent() == []

    async def test_stale_feed_alert_expires(self, session: AsyncSession, broker: FakeBroker) -> None:
        region = region_code()
        home = await make_home(region=region)
        source = await new_source(session, region)
        await feeds.ingest_post(session, source, post(START))
        broker.published.clear()

        later = datetime.now(UTC) + timedelta(hours=get_settings().alert_feed_max_hours + 1)
        expired = await feeds.expire_stale_alerts(session, later)
        assert expired >= 1
        assert await active_alerts(session, home) == []
        texts = [m["text"] for m in broker.sent(chat_id=home.chat_id)]
        assert texts[0].startswith("⏱ Прошло") and texts[1].startswith("✅ Отбой")


class TestSources:
    async def test_default_sources_are_idempotent(self, session: AsyncSession) -> None:
        await feeds.ensure_default_sources()
        assert await feeds.ensure_default_sources() == 0
        refs = set(await session.scalars(select(AlertSource.ref).where(AlertSource.region == "RU-ULY")))
        assert {"mchs_ulyanovsk", "https://73.mchs.gov.ru/deyatelnost/press-centr/operativnaya-informaciya/rss"} <= refs

    async def test_add_source_validates_and_updates(self) -> None:
        ref = f"chan{next_id()}"
        created = await feeds.add_source(" ru-uly ", "telegram_web", f" @{ref} ", "Канал")
        assert (created.region, created.ref, created.title, created.enabled) == ("RU-ULY", ref, "Канал", True)
        updated = await feeds.add_source("RU-SAM", "telegram_web", ref, "", enabled=False)
        assert updated.id == created.id
        assert (updated.region, updated.title, updated.enabled) == ("RU-SAM", "Канал", False)
        odd = await feeds.add_source("XX-ZZZ", "mchs_rss", f"https://example.org/{ref}.rss", "")
        assert odd.title == f"https://example.org/{ref}.rss"

        for region, kind, value in (
            ("Ульяновск", "telegram_web", "x"),
            ("RU-ULY", "fax", "x"),
            ("RU-ULY", "vk_wall", " "),
        ):
            with pytest.raises(ValueError):
                await feeds.add_source(region, kind, value, "")


TELEGRAM_PAGE = """
<div class="tgme_widget_message" data-post="{ref}/41">
  <div class="tgme_widget_message_text js-message_text">Старая новость о погоде</div>
  <a class="tgme_widget_message_date" href="https://t.me/{ref}/41"><time datetime="{old}"></time></a>
</div>
<div class="tgme_widget_message" data-post="{ref}/42">
  <div class="tgme_widget_message_text js-message_text">Внимание! Беспилотная опасность!<br>Отойдите от окон.</div>
  <a class="tgme_widget_message_date" href="https://t.me/{ref}/42"><time datetime="{new}"></time></a>
</div>
"""


class TestPolling:
    async def test_poll_reads_sources_and_starts_alert(
        self, session: AsyncSession, internet: FakeInternet, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        region = region_code()
        home = await make_home(region=region)
        good = await new_source(session, region, last_post_id="40")
        broken = await new_source(session, region, ref=f"broken_{region}")
        rss = await new_source(session, region, type="mchs_rss", ref=f"https://example.org/{region}.rss")
        vk = await new_source(session, region, type="vk_wall", ref="-123")
        good_id, good_ref, broken_id, rss_id, vk_id = good.id, good.ref, broken.id, rss.id, vk.id
        now = datetime.now(UTC)

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == f"/s/{good_ref}":
                page = TELEGRAM_PAGE.format(
                    ref=good_ref,
                    old=(now - timedelta(hours=5)).isoformat(),
                    new=(now - timedelta(minutes=2)).isoformat(),
                )
                return httpx.Response(200, text=page)
            if request.url.host == "example.org":
                return httpx.Response(200, text="<rss><channel><item><title>Новость")
            return httpx.Response(503, text="unavailable")

        internet.handler = handler
        # опрашиваем только источники этого теста (VK без токена пропускается и так)
        monkeypatch.setattr(feeds, "_is_due", lambda s, now_, settings: s.region == region and s.type != "vk_wall")
        await feeds.poll_sources_once(now)

        good_row = await source_row(good_id)
        assert good_row.last_post_id == "42" and good_row.last_error is None
        assert "503" in ((await source_row(broken_id)).last_error or "")
        assert "RSS не разобрать" in ((await source_row(rss_id)).last_error or "")
        assert (await source_row(vk_id)).last_checked_at is None
        (alert,) = await active_alerts(session, home)
        assert alert.source == f"feed:telegram_web:{good_ref}:42"

    def test_due_rules(self) -> None:
        settings = get_settings()
        now = datetime.now(UTC)

        def src(kind: str, checked: datetime | None = None) -> AlertSource:
            return AlertSource(region="RU-ULY", type=kind, ref="x", last_checked_at=checked)

        assert feeds._is_due(src("telegram_web", now), now, settings)
        assert not feeds._is_due(src("max_channel"), now, settings)
        assert not feeds._is_due(src("vk_wall"), now, settings)
        assert not feeds._is_due(src("mchs_rss", now - timedelta(minutes=1)), now, settings)
        assert feeds._is_due(src("mchs_rss", now - timedelta(minutes=10)), now, settings)

    async def test_vk_wall_fetch(self, internet: FakeInternet, monkeypatch: pytest.MonkeyPatch) -> None:
        source = AlertSource(region="RU-ULY", type="vk_wall", ref="mchs73", title="ВК")
        async with httpx.AsyncClient() as http:
            with pytest.raises(feeds.FeedError, match="VK_SERVICE_TOKEN"):
                await feeds.fetch_new_posts(http, source)
            monkeypatch.setattr(get_settings(), "vk_service_token", SimpleNamespace(get_secret_value=lambda: "tok"))
            internet.handler = lambda request: httpx.Response(
                200, json={"response": {"items": [{"id": 5, "owner_id": -7, "date": 1_790_000_000, "text": "Отбой"}]}}
            )
            (item,) = await feeds.fetch_new_posts(http, source)
            assert (item.post_id, item.url) == ("5", "https://vk.com/wall-7_5")
            assert internet.requests[-1].url.params["domain"] == "mchs73"
            assert await feeds.fetch_new_posts(http, AlertSource(region="RU-ULY", type="max_channel", ref="1")) == []
            internet.handler = lambda request: httpx.Response(500)
            with pytest.raises(feeds.FeedError):
                await feeds.fetch_new_posts(http, AlertSource(region="RU-ULY", type="vk_wall", ref="-1"))

    async def test_run_forever_respects_switch(self, monkeypatch: pytest.MonkeyPatch) -> None:
        await feeds.run_forever()  # выключено в тестах: сразу выходит
        calls: list[str] = []

        async def poll(now: datetime | None = None) -> None:
            calls.append("poll")

        async def expire(session: AsyncSession, now: datetime | None = None) -> int:
            calls.append("expire")
            return 0

        async def stop(_: float) -> None:
            raise asyncio.CancelledError

        monkeypatch.setattr(get_settings(), "alert_feeds_enabled", True)
        monkeypatch.setattr(feeds, "poll_sources_once", poll)
        monkeypatch.setattr(feeds, "expire_stale_alerts", expire)
        monkeypatch.setattr(feeds, "asyncio", SimpleNamespace(sleep=stop))
        with pytest.raises(asyncio.CancelledError):
            await feeds.run_forever()
        assert calls == ["poll", "expire"]


class TestChannelPosts:
    async def test_whitelisted_max_channel_starts_alert(self, session: AsyncSession) -> None:
        region = region_code()
        home = await make_home(region=region)
        channel_id = -(9_000_000 + next_id())
        source_id = (await new_source(session, region, type="max_channel", ref=str(channel_id))).id
        message = {
            "recipient": {"chat_id": channel_id, "chat_type": "channel"},
            "body": {"mid": "mid.777", "text": START},
            "timestamp": int(datetime.now(UTC).timestamp() * 1000),
        }
        assert await feeds.ingest_channel_post(message) is True
        (alert,) = await active_alerts(session, home)
        assert alert.source == f"feed:max_channel:{channel_id}:mid.777"
        assert (await source_row(source_id)).last_post_id == "mid.777"

    async def test_unknown_channel_and_empty_post_are_ignored(self) -> None:
        assert await feeds.ingest_channel_post({"recipient": {"chat_id": -1}, "body": {"text": START}}) is False
        assert await feeds.ingest_channel_post({"recipient": {"chat_id": -1}, "body": {"text": " "}}) is False
        assert await feeds.ingest_channel_post({"recipient": {}, "body": {"text": START}}) is False
