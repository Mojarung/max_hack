"""Кузя без мини-приложения: заявка с фото и подтверждением, карточки, голос кнопкой, статусы, списки и выбор дома."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from fakes import FakeBroker, FakeInternet, FakeMinio
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.bot import handlers, screens
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.modules.events.models import Event, EventParticipant
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.models import Issue
from domovoy.modules.market.models import Listing
from domovoy.modules.safety.service import NO_SHELTERS_ADVICE
from domovoy.modules.users.models import House, Membership, User
from domovoy.worker import main as worker
from integration.helpers import (
    REPLY_TO_BOT,
    FakeGateway,
    Home,
    callback_update,
    make_home,
    message_update,
    payloads,
    png_bytes,
    png_data_url,
)

pytestmark = pytest.mark.integration


async def handle(update_: dict[str, Any], gw: FakeGateway) -> None:
    await handlers.HANDLERS[update_["update_type"]](update_, gw)


async def press(
    gw: FakeGateway, user: User, payload: str, *, chat_id: int | None = None, group: bool = False, mid: str = "mid.btn"
) -> str:
    """Нажатие кнопки; по умолчанию в личке жителя. Возвращает всплывающее уведомление."""
    target = user.max_user_id if chat_id is None and not group else chat_id
    await handle(callback_update(user, target, payload, group=group, mid=mid), gw)
    return gw.answers[-1]


async def write(gw: FakeGateway, user: User, text: str = "", *, photos: list[str] | None = None) -> dict[str, Any]:
    await handle(message_update(user, user.max_user_id, text, group=False, photos=photos), gw)
    return gw.last


async def new_issue(home: Home, text: str, author: User | None = None) -> Issue:
    async with get_sessionmaker()() as s:
        user = await s.get(User, (author or home.residents[0]).id)
        house = await s.get(House, home.house.id)
        assert user and house
        return await issues.create_issue(s, user=user, house=house, description=text)


async def make_sent(issue_id: int, *, overdue: bool = False) -> None:
    now = datetime.now(UTC)
    deadline = now - timedelta(hours=1) if overdue else now + timedelta(hours=50)
    async with get_sessionmaker()() as s:
        await s.execute(
            update(Issue).where(Issue.id == issue_id).values(status="sent", sent_at=now, deadline_at=deadline)
        )
        await s.commit()


class TestReportInGroup:
    async def test_report_edit_and_send(self, home: Home, broker: FakeBroker, session: AsyncSession) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        assert await press(gw, user, "menu:report", chat_id=home.chat_id, group=True) == "Открываю"
        assert gw.last["text"].startswith("📸 Ответьте на это сообщение")

        reply = message_update(user, home.chat_id, "Течёт крыша над 9 этажом во втором подъезде", link=REPLY_TO_BOT)
        await handle(reply, gw)
        card = gw.last
        assert card["text"].startswith("📋 **Проверьте заявку**")
        assert "🏷 Категория: Кровля и протечки" in card["text"] and f"👷 Кто отвечает: {home.uk.name}" in card["text"]
        assert payloads(card["buttons"])[-3:] == ["report:send", "report:edit", "report:cancel"]

        assert await press(gw, user, "report:edit", chat_id=home.chat_id, group=True) == "Жду новый текст"
        await handle(message_update(user, home.chat_id, "Кузя, течёт крыша на девятом этаже", link=REPLY_TO_BOT), gw)
        assert "течёт крыша на девятом этаже" in gw.last["text"]

        broker.published.clear()
        assert await press(gw, user, "report:send", chat_id=home.chat_id, group=True) == "Заявка создана"
        issue = await session.scalar(select(Issue).where(Issue.house_id == home.house.id))
        assert issue is not None and issue.description == "течёт крыша на девятом этаже"
        assert gw.last["text"].startswith(f"✅ Заявка №{issue.id}")
        assert payloads(gw.last["buttons"]) == [f"issue:{issue.id}"]
        assert broker.sent(chat_id=home.chat_id)[0]["ref"] == {"issue_id": issue.id}

    async def test_cancel_stale_and_short_text(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[1]
        assert (
            await press(gw, user, "report:send", chat_id=home.chat_id, group=True) == "Черновик устарел, начните заново"
        )
        await press(gw, user, "menu:report", chat_id=home.chat_id, group=True)
        await handle(message_update(user, home.chat_id, "Кузя, течь", link=REPLY_TO_BOT), gw)
        assert gw.last["text"] == "Опишите чуть подробнее: что случилось и где."
        assert await press(gw, user, "report:cancel", chat_id=home.chat_id, group=True) == "Отменено"
        assert gw.last["text"] == "Отменил, заявка не отправлена."

    async def test_card_offers_existing_issue(self, home: Home) -> None:
        existing = await new_issue(home, "Сломаны качели на детской площадке")
        gw = FakeGateway()
        user = home.residents[1]
        await press(gw, user, "menu:report", chat_id=home.chat_id, group=True)
        await handle(message_update(user, home.chat_id, "Кузя, сломаны качели на детской площадке"), gw)
        assert "Похоже, такая заявка уже есть" in gw.last["text"]
        assert f"vote:{existing.id}:card" in payloads(gw.last["buttons"])

        note = await press(gw, user, f"vote:{existing.id}:card", chat_id=home.chat_id, group=True, mid="mid.card")
        assert note == "Голос учтён: 2 из 3"
        assert gw.edits[-1]["mid"] == "mid.card" and "Поддержали 2 из 3" in gw.edits[-1]["text"]

    async def test_gas_card_goes_to_emergency_service(self, home: Home, session: AsyncSession) -> None:
        gw = FakeGateway()
        user = home.residents[2]
        await press(gw, user, "menu:report", chat_id=home.chat_id, group=True)
        await handle(message_update(user, home.chat_id, "Кузя, в подъезде пахнет газом", link=REPLY_TO_BOT), gw)
        assert gw.last["text"].startswith("🚨 Запах газа")
        assert payloads(gw.last["buttons"])[0] == "report:send"
        await press(gw, user, "report:send", chat_id=home.chat_id, group=True)
        assert "сразу отправлена исполнителю" in gw.last["text"]
        issue = await session.scalar(select(Issue).where(Issue.house_id == home.house.id))
        assert issue is not None and issue.status == "sent" and issue.category == "gas"


class TestReportWithPhotos:
    async def test_photo_first_then_text(self, home: Home, minio: FakeMinio, session: AsyncSession) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        asked = await write(gw, user, photos=[png_data_url("red")])
        assert asked["text"].startswith("Фото получил (1)")
        card = await write(gw, user, "Сломаны качели во дворе")
        (key,) = card["photos"]
        assert key.startswith(f"issues/{home.house.id}/") and key in minio.objects
        assert "📷 Фото: 1" in card["text"]
        # к открытой карточке можно дослать ещё фото
        more = await write(gw, user, photos=[png_data_url("blue")])
        assert "📷 Фото: 2" in more["text"]

        await press(gw, user, "report:send")
        issue = await session.scalar(select(Issue).where(Issue.house_id == home.house.id))
        assert issue is not None and len(issue.photos) == 2 and issue.photos[0] == key

    async def test_photo_with_caption_and_public_download(
        self, home: Home, internet: FakeInternet, minio: FakeMinio
    ) -> None:
        internet.handler = lambda request: httpx.Response(200, content=png_bytes("green"))
        gw = FakeGateway()
        card = await write(gw, home.residents[1], "Кузя, течёт кран в подвале", photos=["https://i.oneme.ru/i?r=abc"])
        assert card["text"].startswith("📋 **Проверьте заявку**")
        assert len(card["photos"]) == 1 and card["photos"][0] in minio.objects
        assert str(internet.requests[-1].url) == "https://i.oneme.ru/i?r=abc"

    async def test_unsafe_or_broken_photos_are_skipped(self, home: Home, internet: FakeInternet) -> None:
        internet.handler = lambda request: httpx.Response(200, content=b"not an image")
        gw = FakeGateway()
        urls = ["http://i.max.ru/1.jpg", "https://10.0.0.5/2.jpg", "https://i.oneme.ru/broken"]
        reply = await write(gw, home.residents[2], photos=urls)
        assert reply["text"].startswith("Фото получил (0)")
        assert [str(r.url) for r in internet.requests] == ["https://i.oneme.ru/broken"]

    async def test_data_url_is_refused_outside_mock(self, home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
        gw = FakeGateway()
        user = home.residents[2]
        monkeypatch.setattr(get_settings(), "mock_max", False)
        reply = await write(gw, user, "Сломан домофон в подъезде", photos=[png_data_url()])
        assert "📷 Фото: 0" in reply["text"]


class TestLegacyButtons:
    async def test_vote_from_issue_message_in_house_chat(self, home: Home, broker: FakeBroker) -> None:
        issue = await new_issue(home, "Не горит свет на лестнице")
        gw = FakeGateway()
        broker.published.clear()
        assert await press(gw, home.residents[1], f"vote:{issue.id}", chat_id=home.chat_id, group=True) == (
            "Голос учтён: 2 из 3"
        )
        edit = gw.edits[-1]
        assert edit["text"] == issues.issue_chat_text(await reload(issue.id))
        assert "Поддерживаю (2/3)" in edit["buttons"][0][0]["text"]
        # голос из самого сообщения заявки: обновлять его отдельно не нужно
        assert broker.payloads("bot.issue_refresh") == []

        twice = await press(gw, home.residents[1], f"vote:{issue.id}", chat_id=home.chat_id, group=True)
        assert twice == "Вы уже поддержали эту заявку"
        last = await press(gw, home.residents[2], f"vote:{issue.id}", chat_id=home.chat_id, group=True)
        assert last == "Голосов хватило! Отправляю обращение 📨"
        assert broker.payloads("issue.dispatch") == [{"issue_id": issue.id}]

    async def test_newcomer_in_house_chat_can_vote_stranger_cannot(self, home: Home) -> None:
        issue = await new_issue(home, "Сломан домофон")
        gw = FakeGateway()
        newcomer = User(max_user_id=8_500_000 + issue.id, first_name="Новенький", last_name="")
        assert await press(gw, newcomer, f"vote:{issue.id}", chat_id=home.chat_id, group=True) == "Голос учтён: 2 из 3"
        denied = await press(gw, home.outsider, f"vote:{issue.id}")
        assert denied == "Эта кнопка для жителей другого дома"
        assert await press(gw, home.admin, "vote:999999", chat_id=home.chat_id, group=True) == "Заявка не найдена"

    async def test_join_event_from_announcement(self, home: Home, session: AsyncSession) -> None:
        ev = Event(
            house_id=home.house.id,
            author_id=home.admin.id,
            title="Праздник двора",
            kind="holiday",
            starts_at=datetime.now(UTC) + timedelta(days=2),
            place="Двор",
            participants_count=1,
        )
        session.add(ev)
        await session.commit()
        gw = FakeGateway()
        note = await press(gw, home.residents[0], f"join:{ev.id}", chat_id=home.chat_id, group=True, mid="mid.ev")
        assert note == "Записал! Напомню заранее 🙌"
        assert gw.edits[-1]["mid"] == "mid.ev" and "Иду (2)" in gw.edits[-1]["buttons"][0][0]["text"]
        assert await press(gw, home.residents[0], "join:999999", chat_id=home.chat_id, group=True) == (
            "Событие не найдено"
        )

    async def test_stale_buttons(self, home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
        gw = FakeGateway()
        assert await press(gw, home.admin, "something:1") == "Кнопка устарела"
        assert await press(gw, home.admin, "vote:abc") == "Кнопка устарела"
        await handle(callback_update(home.admin, None, "menu:issues"), gw)
        assert gw.answers[-1] == "Кнопка устарела"
        assert await press(gw, home.admin, "status:1:voting") == "Кнопка устарела"
        assert await press(gw, home.admin, "menu:report:extra:zzz") == "Открываю"

        monkeypatch.setattr(get_settings(), "pilot_house_fallback", False)
        stranger = User(max_user_id=8_600_000 + home.house.id, first_name="Гость", last_name="")
        assert await press(gw, stranger, "menu:issues") == "Добавьте Кузю в чат вашего дома"


async def reload(issue_id: int) -> Issue:
    async with get_sessionmaker()() as s:
        issue = await s.get(Issue, issue_id)
        assert issue is not None
        return issue


class TestIssueCard:
    async def test_voting_card(self, home: Home) -> None:
        issue = await new_issue(home, "Сломаны качели на детской площадке")
        gw = FakeGateway()
        assert await press(gw, home.residents[1], f"issue:{issue.id}") == "Карточка заявки"
        text = gw.last["text"]
        assert text.startswith(f"📋 **{issue.title}** · №{issue.id}")
        assert "👍 Поддержали 1 из 3" in text and "⏱ Срок по закону:" in text and "🕑 **Ход заявки**" in text
        assert payloads(gw.last["buttons"])[0] == f"vote:{issue.id}:card"
        # автор уже голосовал: кнопки голоса у него нет
        await press(gw, home.residents[0], f"issue:{issue.id}")
        assert not any(p.startswith("vote:") for p in payloads(gw.last["buttons"]))
        assert await press(gw, home.residents[0], "issue:999999") == "Заявка не найдена"

    async def test_status_buttons_appeal_and_complaint(self, home: Home) -> None:
        issue = await new_issue(home, "Не работает лифт в третьем подъезде")
        gw = FakeGateway()
        author, neighbour = home.residents[0], home.residents[1]
        assert await press(gw, author, f"appeal:{issue.id}") == "Отправил текст"
        assert "Обращение ещё не отправлено" in gw.last["text"]
        assert await press(gw, author, f"status:{issue.id}:resolved") == (
            "Статус можно менять после отправки обращения"
        )

        await make_sent(issue.id)
        await worker.dispatch_issue(issue.id)
        await press(gw, author, f"issue:{issue.id}")
        assert "⏱ Срок: до" in gw.last["text"] and "осталось 2 дн" in gw.last["text"]
        assert {f"status:{issue.id}:in_progress", f"status:{issue.id}:resolved", f"appeal:{issue.id}"} <= set(
            payloads(gw.last["buttons"])
        )
        await press(gw, author, f"appeal:{issue.id}")
        assert gw.last["text"].startswith("📄 **Текст обращения**") and "ОБРАЩЕНИЕ №" in gw.last["text"]
        await press(gw, author, f"complaint:{issue.id}")
        assert "Жалобы пока нет" in gw.last["text"]

        denied = await press(gw, neighbour, f"status:{issue.id}:in_progress", mid="mid.card")
        assert denied == "Менять статус может автор заявки или администратор дома"
        assert await press(gw, author, f"status:{issue.id}:in_progress", mid="mid.card") == "Отметил: в работе"
        assert "🔧 В работе" in gw.edits[-1]["text"]

        await make_sent(issue.id, overdue=True)
        await worker.escalate_overdue()
        await press(gw, author, f"issue:{issue.id}")
        assert "просрочено на" in gw.last["text"] and f"complaint:{issue.id}" in payloads(gw.last["buttons"])
        await press(gw, author, f"complaint:{issue.id}")
        assert gw.last["text"].startswith("⚖️ **Жалоба в Госжилинспекцию**")

        assert await press(gw, home.admin, f"status:{issue.id}:resolved") == "Отметил: решено 🎉"


class TestLists:
    async def test_issue_lists(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[2]
        await press(gw, user, "menu:issues")
        assert gw.last["text"] == "Открытых заявок нет. Дом в порядке 🏠"
        await press(gw, user, "menu:mine")
        assert gw.last["text"] == "У вас пока нет заявок."

        first = await new_issue(home, "Сломаны качели на детской площадке", author=user)
        second = await new_issue(home, "Не горит свет на лестнице")
        await make_sent(second.id)
        await press(gw, user, "menu:issues")
        assert gw.last["text"].startswith("📋 **Заявки дома**")
        assert "голосов 1 из 3" in gw.last["text"] and "осталось" in gw.last["text"]
        assert payloads(gw.last["buttons"])[:2] == [f"issue:{second.id}", f"issue:{first.id}"]
        await press(gw, user, "menu:mine")
        assert gw.last["text"].startswith("🗂 **Мои заявки**")
        assert payloads(gw.last["buttons"])[0] == f"issue:{first.id}:mine"
        assert payloads(gw.last["buttons"])[-1] == "menu:menu"

    async def test_events_join_and_leave(self, home: Home, session: AsyncSession) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await press(gw, user, "menu:events")
        assert gw.last["text"].startswith("Ближайших событий нет")
        ev = Event(
            house_id=home.house.id,
            author_id=home.admin.id,
            title="Собрание жителей",
            kind="meeting",
            starts_at=datetime.now(UTC) + timedelta(days=3),
            place="Холл",
            max_participants=10,
            participants_count=1,
        )
        session.add(ev)
        await session.flush()
        session.add(EventParticipant(event_id=ev.id, user_id=home.admin.id))
        await session.commit()

        await press(gw, user, "menu:events")
        assert "Собрание жителей" in gw.last["text"] and "свободно 9" in gw.last["text"]
        assert payloads(gw.last["buttons"])[0] == f"join:{ev.id}:list"
        assert await press(gw, user, f"join:{ev.id}:list", mid="mid.list") == "Записал! Напомню заранее 🙌"
        assert payloads(gw.edits[-1]["buttons"])[0] == f"leave:{ev.id}:list"
        assert await press(gw, user, f"leave:{ev.id}:list", mid="mid.list") == "Отменил запись"
        assert await press(gw, user, f"leave:{ev.id}:list") == "Вы не были записаны"
        assert await press(gw, user, "join:999999:list") == "Событие не найдено"

    async def test_market_listing_and_contact(self, home: Home, broker: FakeBroker, session: AsyncSession) -> None:
        gw = FakeGateway()
        buyer, seller = home.residents[1], home.residents[0]
        await press(gw, buyer, "menu:market")
        assert gw.last["text"] == "В «Вещах соседей» пока пусто."
        item = Listing(
            house_id=home.house.id, author_id=seller.id, title="Дрель", description="С набором свёрл", price=0
        )
        paid = Listing(house_id=home.house.id, author_id=seller.id, title="Шкаф", description="", price=3000)
        session.add_all([item, paid])
        await session.commit()

        await press(gw, buyer, "menu:market")
        assert "Дрель: даром" in gw.last["text"] and "Шкаф: 3000 ₽" in gw.last["text"]
        assert await press(gw, buyer, f"listing:{item.id}") == "Объявление"
        assert "Продавец: Олег Первый, кв. 2" in gw.last["text"]
        assert payloads(gw.last["buttons"])[0] == f"contact:{item.id}"
        await press(gw, seller, f"listing:{item.id}")
        assert payloads(gw.last["buttons"]) == [f"listing_{item.id}", "menu:market"]

        broker.published.clear()
        assert await press(gw, buyer, f"contact:{item.id}") == "Передал продавцу, он ответит вам в личных сообщениях"
        assert broker.sent(user_id=seller.max_user_id)
        assert await press(gw, buyer, f"contact:{item.id}") == "Уже передал продавцу, ждите ответа в личных сообщениях"
        assert await press(gw, seller, f"contact:{paid.id}") == "Это ваше объявление"
        assert await press(gw, buyer, "listing:999999") == "Объявление не найдено"

    async def test_shelters_profile_and_menu(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await press(gw, user, "menu:shelters")
        assert gw.last["text"].startswith("🛡 **Ближайшие укрытия**")
        assert payloads(gw.last["buttons"])[0].startswith("https://yandex.ru/maps/")
        await press(gw, user, "menu:profile")
        assert gw.last["text"].startswith("🏆 **Олег Первый**") and "Уровень 1 · Новосёл" in gw.last["text"]
        await press(gw, user, "menu")
        assert gw.last["text"] == f"🏠 {home.house.title}. Что сделать?"

        far = await make_home(lat=-45.0, lon=170.0)
        await press(gw, far.residents[0], "menu:shelters")
        assert gw.last["text"] == NO_SHELTERS_ADVICE

    async def test_house_choice(self, home: Home, session: AsyncSession) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await press(gw, user, "menu:houses")
        assert gw.last["text"].startswith(f"Ваш дом: **{home.house.title}**")

        dacha = House(max_chat_id=None, title="Дача у реки", address="СНТ")
        session.add(dacha)
        await session.flush()
        session.add(Membership(user_id=user.id, house_id=dacha.id))
        await session.commit()
        dacha_id = dacha.id
        await press(gw, user, "menu:houses")
        assert payloads(gw.last["buttons"]) == [f"house:{home.house.id}", f"house:{dacha.id}", "menu:menu"]
        assert gw.last["buttons"][0][0]["text"].startswith("✓ ")

        assert await press(gw, user, f"house:{dacha.id}") == "Дом выбран"
        assert gw.last["text"] == "Готово, ваш дом: **Дача у реки**."
        session.expire_all()
        assert (await session.get(User, user.id)).active_house_id == dacha_id  # type: ignore[union-attr]
        assert await press(gw, user, "house:999999") == "Этого дома нет в вашем списке"

        # черновик начат в старом доме, а житель переключился: отправить его нельзя
        await press(gw, user, f"house:{home.house.id}")
        await press(gw, user, "menu:report")
        await write(gw, user, "Течёт кран в подвале")
        await press(gw, user, f"house:{dacha_id}")
        assert await press(gw, user, "report:send") == "Вы сменили дом, начните заявку заново"


class TestScreens:
    """Кнопки меняют экран на месте, «Назад» ведёт обратно, старые экраны не копятся в чате."""

    async def test_navigation_edits_one_message(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await press(gw, user, "menu")
        screen = gw.last["mid"]
        await press(gw, user, "menu:issues", mid=screen)
        assert len(gw.sent) == 1 and gw.edits[-1]["mid"] == screen
        assert gw.edits[-1]["text"] == "Открытых заявок нет. Дом в порядке 🏠"
        assert payloads(gw.edits[-1]["buttons"])[-1] == "menu:menu"
        await press(gw, user, "menu:menu", mid=screen)
        assert gw.edits[-1]["text"] == f"🏠 {home.house.title}. Что сделать?"

        issue = await new_issue(home, "Не работает лифт в третьем подъезде", author=user)
        await press(gw, user, "menu:mine", mid=screen)
        await press(gw, user, f"issue:{issue.id}:mine", mid=screen)
        card = gw.edits[-1]
        assert card["text"].startswith(f"📋 **{issue.title}**") and payloads(card["buttons"])[-1] == "menu:mine"
        await make_sent(issue.id)
        await worker.dispatch_issue(issue.id)
        await press(gw, user, f"appeal:{issue.id}:mine", mid=screen)
        assert gw.edits[-1]["text"].startswith("📄 **Текст обращения**")
        assert payloads(gw.edits[-1]["buttons"]) == [f"issue:{issue.id}:mine"]
        assert len(gw.sent) == 1 and gw.deleted == []

    async def test_new_screen_replaces_old_and_cancel_cleans_draft(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[1]
        await write(gw, user, "/меню")
        first = gw.last["mid"]
        await write(gw, user, "/события")
        assert gw.deleted == [first]

        await press(gw, user, "menu:report")
        prompt = gw.last["mid"]
        assert await press(gw, user, "report:cancel", mid=prompt) == "Отменено"
        assert prompt in gw.deleted and gw.last["text"] == "Отменил, заявка не отправлена."

    async def test_group_screen_deletes_itself(self, home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(screens, "SCREEN_TTL_S", 0.05)
        gw = FakeGateway()
        await handle(message_update(home.residents[0], home.chat_id, "/заявки"), gw)
        screen = gw.last["mid"]
        assert gw.last["chat_id"] == home.chat_id and gw.deleted == []
        await asyncio.sleep(0.15)
        assert gw.deleted == [screen]


ISSUE_TEXTS = (
    "Сломаны качели на детской площадке",
    "Не горит свет на лестнице третьего этажа",
    "Течёт кран в подвале второго подъезда",
    "Не работает домофон в первом подъезде",
    "Разбито окно между пятым и шестым этажом",
    "Не вывозят мусор с контейнерной площадки",
    "Сломан доводчик двери в четвёртом подъезде",
)


class TestPages:
    """Списки по пять позиций со стрелками, подпись «Показано: 6-7 из 7», «Назад» на ту же страницу."""

    async def test_issue_list_pages_and_back_to_same_page(self, home: Home) -> None:
        created = [await new_issue(home, text) for text in ISSUE_TEXTS]
        gw = FakeGateway()
        user = home.residents[1]
        await press(gw, user, "menu:issues")
        screen = gw.last["mid"]
        assert "Показано: 1-5 из 7" in gw.last["text"]
        keys = payloads(gw.last["buttons"])
        assert sum(k.startswith("issue:") for k in keys) == 5 and "menu:issues:2" in keys

        await press(gw, user, "menu:issues:2", mid=screen)
        page2 = gw.edits[-1]
        assert "Показано: 6-7 из 7" in page2["text"] and "\n6. " in page2["text"]
        keys = payloads(page2["buttons"])
        assert f"issue:{created[0].id}:issues:2" in keys and "menu:issues:1" in keys and "menu:issues:3" not in keys

        await press(gw, user, f"issue:{created[0].id}:issues:2", mid=screen)
        assert payloads(gw.edits[-1]["buttons"])[-1] == "menu:issues:2"
        assert len(gw.sent) == 1

    async def test_events_page_two_join_stays_on_page(self, home: Home, session: AsyncSession) -> None:
        start = datetime.now(UTC) + timedelta(days=2)
        evs = [
            Event(
                house_id=home.house.id,
                author_id=home.admin.id,
                title=f"Встреча {n}",
                kind="meeting",
                starts_at=start + timedelta(days=n),
                place="Холл",
            )
            for n in range(6)
        ]
        session.add_all(evs)
        await session.commit()
        gw = FakeGateway()
        user = home.residents[0]
        await press(gw, user, "menu:events")
        screen = gw.last["mid"]
        assert "Показано: 1-5 из 6" in gw.last["text"]
        await press(gw, user, "menu:events:2", mid=screen)
        assert "Показано: 6 из 6" in gw.edits[-1]["text"]
        assert payloads(gw.edits[-1]["buttons"])[0] == f"join:{evs[5].id}:list:2"
        assert await press(gw, user, f"join:{evs[5].id}:list:2", mid=screen) == "Записал! Напомню заранее 🙌"
        assert "Показано: 6 из 6" in gw.edits[-1]["text"]
        assert payloads(gw.edits[-1]["buttons"])[0] == f"leave:{evs[5].id}:list:2"

    async def test_market_page_two_listing_back(self, home: Home, session: AsyncSession) -> None:
        items = [
            Listing(house_id=home.house.id, author_id=home.admin.id, title=f"Вещь {n}", description="", price=n)
            for n in range(6)
        ]
        for item in items:
            session.add(item)
            await session.flush()
        await session.commit()
        gw = FakeGateway()
        user = home.residents[0]
        await press(gw, user, "menu:market")
        screen = gw.last["mid"]
        assert "Показано: 1-5 из 6" in gw.last["text"] and "menu:market:2" in payloads(gw.last["buttons"])
        await press(gw, user, "menu:market:2", mid=screen)
        oldest = f"listing:{items[0].id}:2"
        assert oldest in payloads(gw.edits[-1]["buttons"])
        await press(gw, user, oldest, mid=screen)
        assert payloads(gw.edits[-1]["buttons"])[-1] == "menu:market:2"


class TestSellInChat:
    """«Разместить свою вещь» прямо в личке: одно сообщение с названием и ценой, фото, карточка, кнопка."""

    async def test_sell_with_photo(self, home: Home, minio: FakeMinio, session: AsyncSession) -> None:
        gw = FakeGateway()
        user = home.residents[1]
        await press(gw, user, "menu:market")
        screen = gw.last["mid"]
        assert "sell:start" in payloads(gw.last["buttons"])
        assert await press(gw, user, "sell:start", mid=screen) == "Открываю"
        assert gw.edits[-1]["text"].startswith("🛍 Что отдаёте или продаёте?")

        card = await write(gw, user, "Детская коляска, почти новая, 3000 ₽", photos=[png_data_url()])
        assert "**Детская коляска** · 3000 ₽" in card["text"] and "🏷 Раздел: Детское" in card["text"]
        (key,) = card["photos"]
        assert key.startswith("listings/") and key in minio.objects

        assert await press(gw, user, "sell:send", mid=card["mid"]) == "Объявление размещено"
        item = await session.scalar(select(Listing).where(Listing.house_id == home.house.id))
        assert item is not None
        assert (item.title, item.description, item.price, item.category, item.photos) == (
            "Детская коляска",
            "Почти новая",
            3000,
            "kids",
            [key],
        )
        # карточка остаётся в переписке без кнопок, ниже экран с объявлением
        assert {"mid": card["mid"], "text": None, "buttons": []}.items() <= gw.edits[-1].items()
        assert gw.last["text"].startswith("✅ Объявление «Детская коляска» размещено")
        assert payloads(gw.last["buttons"]) == [f"listing:{item.id}", "menu:menu"]
        assert await press(gw, user, "sell:send", mid=card["mid"]) == "Черновик устарел, начните заново"

    async def test_free_item_edit_and_cancel(self, home: Home, session: AsyncSession) -> None:
        gw = FakeGateway()
        user = home.residents[2]
        await write(gw, user, "/отдать")
        assert gw.last["text"].startswith("🛍 Что отдаёте или продаёте?")
        assert (await write(gw, user, "Ой"))["text"].startswith("Напишите, что это за вещь")
        assert (await write(gw, user, "Шкаф 99999999 ₽"))["text"].startswith("Цена слишком большая")

        card = await write(gw, user, "Пылесос, работает")
        assert "**Пылесос** · даром" in card["text"] and "Цену я не нашёл" in card["text"]
        assert await press(gw, user, "sell:edit", mid=card["mid"]) == "Жду новый текст"
        card = await write(gw, user, "Отдам даром книги для школьников")
        assert "**Книги для школьников** · даром" in card["text"] and "Цену я не нашёл" not in card["text"]
        # кнопка заявки со старой карточки не отправит объявление как заявку
        assert await press(gw, user, "report:send") == "Черновик устарел, начните заново"

        assert await press(gw, user, "sell:cancel", mid=card["mid"]) == "Отменено"
        assert card["mid"] in gw.deleted and gw.last["text"] == "Отменил, объявление не размещено."
        count = select(func.count()).select_from(Listing).where(Listing.house_id == home.house.id)
        assert await session.scalar(count) == 0
        assert await press(gw, user, "sell:send") == "Черновик устарел, начните заново"

    async def test_photo_first_then_text(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await press(gw, user, "sell:start")
        asked = await write(gw, user, photos=[png_data_url("blue")])
        assert asked["text"].startswith("Фото получил (1). Теперь напишите название и цену")
        card = await write(gw, user, "Дрель на выходные за 300")
        assert "**Дрель на выходные** · 300 ₽" in card["text"] and "📷 Фото: 1" in card["text"]

    async def test_group_chat_sends_seller_to_dm(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await handle(message_update(user, home.chat_id, "/вещи"), gw)
        keys = payloads(gw.last["buttons"])
        assert "sell:start" not in keys and "market" in keys
        await press(gw, user, "sell:start", chat_id=home.chat_id, group=True)
        assert gw.last["text"].startswith("Объявление размещается в личных сообщениях")

    async def test_blocked_listing_keeps_draft(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await write(gw, user, "/продать")
        card = await write(gw, user, "Заработок от 100000 в день, пиши в личку t.me/xxx")
        note = await press(gw, user, "sell:send", mid=card["mid"])
        assert note.startswith("Кузя не пропустил объявление")
        assert await press(gw, user, "sell:edit", mid=card["mid"]) == "Жду новый текст"

    async def test_house_switch_drops_listing_draft(self, home: Home, session: AsyncSession) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        dacha = House(max_chat_id=None, title="Дача у озера", address="СНТ")
        session.add(dacha)
        await session.flush()
        session.add(Membership(user_id=user.id, house_id=dacha.id))
        await session.commit()
        await press(gw, user, "sell:start")
        await write(gw, user, "Стол письменный, 500 ₽")
        await press(gw, user, f"house:{dacha.id}")
        assert await press(gw, user, "sell:send") == "Вы сменили дом, начните заново"
