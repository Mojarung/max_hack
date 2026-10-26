"""Своя вещь в «Вещах соседей» прямо из лички с Кузей, без мини-приложения.

Житель одним сообщением пишет, что отдаёт или продаёт и за сколько, прикладывает до пяти фото,
Кузя показывает карточку объявления, и после «Разместить» соседи видят его в «Вещах соседей».
Черновик общий с заявкой (chat_flows.Draft с kind="listing"): текст и фото ловит тот же обработчик.
В чате дома объявление не размещается: это личное дело жителя, а общий чат не засоряется.
"""

import re
from dataclasses import dataclass

from domovoy.bot import chat_flows as flows
from domovoy.bot.chat_flows import Draft, Who, button
from domovoy.bot.gateway import Buttons, Gateway
from domovoy.core.db import get_sessionmaker
from domovoy.modules.market import service as market
from domovoy.modules.users.models import House, User

MAX_PRICE = 10_000_000
TITLE_MAX = 60
PROMPT = (
    "🛍 Что отдаёте или продаёте? Напишите одним сообщением название и цену, можно приложить до пяти фото.\n\n"
    "Например: «Детская коляска, почти новая, 3000 ₽» или «Книги для школьников, даром»."
)
EXAMPLE = "например «Детская коляска, 3000 ₽» или «Книги для школьников, даром»"

FREE_RE = re.compile(r"\b(?:даром|бесплатно|отда[мю]|в дар|за так)\b", re.IGNORECASE)
# цена с валютой, «за 500», «цена 500» или число в конце сообщения («Шкаф-купе 3000»)
PRICE_RES = (
    re.compile(r"(\d[\d ]{0,9})\s*(?:₽|руб\w*|р\.?)(?!\w)", re.IGNORECASE),
    re.compile(r"\b(?:за|цена:?)\s*(\d[\d ]{0,9})", re.IGNORECASE),
    re.compile(r"(\d{3,8})\s*$"),
)
LEAD_RE = re.compile(r"^(?:(?:продам|продаю|отдам|отдаю|даром|бесплатно)[,:]?\s+)+", re.IGNORECASE)
HEAD_END_RE = re.compile(r"[,.;!?(]| - ")
# раздел по словам: в приложении житель выбирает его сам, здесь угадываем, а карточка показывает итог
CATEGORY_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("kids", ("коляск", "детск", "игрушк", "школьн", "самокат", "манеж", "автокресл", "пелен")),
    ("furniture", ("шкаф", "стол", "стул", "диван", "кроват", "комод", "полк", "кресл", "тумб", "матрас")),
    (
        "electronics",
        ("телевизор", "холодильник", "пылесос", "ноутбук", "телефон", "микроволнов", "чайник", "стиральн", "монитор"),
    ),
    ("clothes", ("куртк", "одежд", "обув", "ботинк", "пальто", "плать", "шуб", "кроссовк", "сапог", "джинс")),
    ("tools", ("дрел", "инструмент", "перфоратор", "шуруповерт", "шуруповёрт", "лестниц", "отвертк", "отвёртк")),
    ("plants", ("рассад", "цвет", "растени", "семен", "горшк", "фикус")),
    ("food", ("варень", "солень", "овощ", "яблок", "картош", "огурц", "заготовк", "банк")),
    ("services", ("помогу", "услуг", "репетитор", "выгул", "присмотр", "починю")),
)


@dataclass(frozen=True)
class Parsed:
    title: str
    description: str
    price: int | None  # None: цену не нашли, вещь уйдёт даром, карточка об этом предупредит
    category: str


def _cap(text: str) -> str:
    return text[:1].upper() + text[1:]


def guess_category(text: str) -> str:
    low = text.lower()
    return next((code for code, words in CATEGORY_WORDS if any(w in low for w in words)), "other")


def parse(text: str) -> Parsed:
    """«Продам детскую коляску, почти новая, 3000 ₽» -> название, описание, цена и раздел."""
    # первая строка - название: перенос строки отделяет его так же, как запятая
    clean = " ".join(text.strip().replace("\n", ". ").split())
    price: int | None = 0 if FREE_RE.search(clean) else None
    if price is None:
        for rx in PRICE_RES:
            if m := rx.search(clean):
                price = int(re.sub(r"\D", "", m.group(1)))
                clean = clean[: m.start()] + clean[m.end() :]
                break
    clean = FREE_RE.sub("", LEAD_RE.sub("", clean.strip()))
    clean = re.sub(r"\s+([,.;:!?)])", r"\1", " ".join(clean.split())).strip(" ,.;:-")
    end = HEAD_END_RE.search(clean)
    head, rest = (clean[: end.start()], clean[end.end() :]) if end else (clean, "")
    title = _cap(head.strip(" ,.;:-")) or _cap(clean)
    return Parsed(
        title=title[:TITLE_MAX].strip(),
        description=_cap(rest.strip(" ,.;:-()"))[:2000],
        price=price,
        category=guess_category(text),
    )


def _cancel_row() -> Buttons:
    return [[button("✖️ Отмена", "sell:cancel")]]


async def start(gw: Gateway, who: Who, mid: str | None = None) -> None:
    if who.is_group:
        text = "Объявление размещается в личных сообщениях: напишите мне, и я помогу 🙂"
        await flows.show(gw, who, mid, text, [flows.back_row()])
        return
    flows.open_draft(who, "listing")
    # вопрос встаёт на место списка вещей: в чате не копятся лишние сообщения
    await flows.show(gw, who, mid, PROMPT, _cancel_row())


async def draft_message(gw: Gateway, who: Who, draft: Draft, text: str, photo_urls: list[str]) -> None:
    """Название с ценой, фото или исправленный текст объявления."""
    if photo_urls:
        room = flows.MAX_DRAFT_PHOTOS - len(draft.photos)
        stored = await flows.store_photos(photo_urls[:room], "listings")
        draft.photos = (draft.photos + stored)[: flows.MAX_DRAFT_PHOTOS]
    if text:
        draft.text = text
    if not draft.text:
        ask = f"Фото получил ({len(draft.photos)}). Теперь напишите название и цену, {EXAMPLE}."
        await gw.send(chat_id=who.chat_id, text=ask, buttons=_cancel_row())
        return
    item = parse(draft.text)
    problem = None
    if len(item.title) < 3:
        problem = f"Напишите, что это за вещь, {EXAMPLE}."
    elif item.price is not None and item.price > MAX_PRICE:
        problem = "Цена слишком большая. Напишите сумму в рублях, например «3000 ₽»."
    if problem:
        draft.text = ""
        await gw.send(chat_id=who.chat_id, text=problem, buttons=_cancel_row())
        return
    draft.stage = "confirm"
    await show_confirm(gw, who, draft, item)


async def show_confirm(gw: Gateway, who: Who, draft: Draft, item: Parsed) -> None:
    lines = ["🛍 **Проверьте объявление**", "", f"**{item.title}** · {flows.price_text(item.price or 0)}"]
    if item.description:
        lines.append(item.description[:400])
    lines += ["", f"🏷 Раздел: {market.CATEGORIES[item.category]}", f"📷 Фото: {len(draft.photos)}"]
    if item.price is None:
        lines += ["", "Цену я не нашёл, поэтому вещь уйдёт даром. Если продаёте, нажмите «Исправить» и укажите цену."]
    buttons: Buttons = [
        [button("✅ Разместить", "sell:send")],
        [button("✏️ Исправить", "sell:edit"), button("✖️ Отмена", "sell:cancel")],
    ]
    # фото прямо в карточке: житель видит, что увидят соседи
    await gw.send(chat_id=who.chat_id, text="\n".join(lines), buttons=buttons, photos=list(draft.photos) or None)


async def action(gw: Gateway, who: Who, name: str, mid: str | None) -> str:
    """Кнопки «Разместить свою вещь», «Разместить», «Исправить», «Отмена». Возвращает всплывающее уведомление."""
    if name == "start":
        await start(gw, who, mid)
        return "Открываю"
    if name == "cancel":
        flows.drop_draft(who, "listing")
        await flows.close_draft(gw, who, mid, "Отменил, объявление не размещено.")
        return "Отменено"
    draft = flows.get_draft(who)
    if draft is None or draft.kind != "listing":
        return "Черновик устарел, начните заново"
    if name == "edit":
        draft.stage = "text"
        text = "Напишите заново название и цену одним сообщением. Фото сохранил."
        await gw.send(chat_id=who.chat_id, text=text, buttons=_cancel_row())
        return "Жду новый текст"
    if name != "send" or not draft.text:
        return "Сначала напишите, что размещаете"
    if draft.house_id != who.house.id:
        flows.drop_draft(who, "listing")
        return "Вы сменили дом, начните заново"
    return await publish(gw, who, draft, mid)


async def publish(gw: Gateway, who: Who, draft: Draft, mid: str | None) -> str:
    item = parse(draft.text)
    async with get_sessionmaker()() as session:
        user = await session.get(User, who.user.id)
        house = await session.get(House, who.house.id)
        if user is None or house is None:
            return "Не нашёл ваш дом"
        # модерация внутри: грубость и реклама вернутся всплывающим уведомлением, черновик останется
        listing = await market.create_listing(
            session,
            user=user,
            house=house,
            title=item.title,
            description=item.description,
            price=item.price or 0,
            category=item.category,
            photos=list(draft.photos),
        )
        listing_id, title = listing.id, listing.title
    flows.drop_draft(who, "listing")
    if mid:
        # карточка остаётся в переписке как память о том, что разместили, а кнопки с неё уходят
        await gw.edit(mid=mid, text=None, buttons=[])
    text = (
        f"✅ Объявление «{title}» размещено в «Вещах соседей». "
        "Когда сосед нажмёт «Написать продавцу», я сразу пришлю вам, кто это."
    )
    buttons: Buttons = [[button("🛍 Посмотреть объявление", f"listing:{listing_id}")], flows.back_row()]
    await flows.show(gw, who, None, text, buttons)
    return "Объявление размещено"
