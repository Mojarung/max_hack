"""Бот в чате дома и в личке: появление в чате, участники, команды, модерация, подсказки и агент Кузи."""

from typing import Any

import pytest
from fakes import FakeBroker
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.bot import handlers
from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.modules.events.models import Event
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.models import Issue
from domovoy.modules.misc_models import Announcement, ModerationLog
from domovoy.modules.users.models import House, Membership, User
from integration.helpers import FakeGateway, Home, make_home, max_user, message_update, next_id, payloads

pytestmark = pytest.mark.integration

RUDE = "Ты дурак, блин"


async def handle(update: dict[str, Any], gw: FakeGateway) -> None:
    """Обработчик апдейта без перехвата ошибок: тест должен видеть падение, а не строку в логе."""
    await handlers.HANDLERS[update["update_type"]](update, gw)


async def dm(gw: FakeGateway, user: User, text: str) -> dict[str, Any]:
    await handle(message_update(user, user.max_user_id, text, group=False), gw)
    return gw.last


async def membership(user_id: int, house_id: int) -> Membership | None:
    async with get_sessionmaker()() as s:
        return await s.scalar(select(Membership).where(Membership.user_id == user_id, Membership.house_id == house_id))


class TestChatLifecycle:
    async def test_bot_added_creates_house_and_greets(self, session: AsyncSession) -> None:
        chat_id = -(2_000_000 + next_id())
        inviter = {"user_id": 8_000_000 + next_id(), "first_name": "Пётр", "last_name": "Новиков"}
        gw = FakeGateway(members=25, title="Дом на Тестовой")
        await handle({"update_type": "bot_added", "chat_id": chat_id, "user": inviter}, gw)

        house = await session.scalar(select(House).where(House.max_chat_id == chat_id))
        assert house is not None
        assert (house.title, house.members_count, house.setup_done) == ("Дом на Тестовой", 25, False)
        user = await session.scalar(select(User).where(User.max_user_id == inviter["user_id"]))
        assert user is not None
        member = await membership(user.id, house.id)
        assert member is not None and member.role == "admin"
        (greeting,) = gw.sent
        assert greeting["chat_id"] == chat_id
        assert greeting["text"].startswith("Всем привет! Теперь я живу в этом чате.")
        assert greeting["buttons"] == handlers.MENU

    async def test_bot_started_in_dm(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await handle({"update_type": "bot_started", "chat_id": user.max_user_id, "user": max_user(user)}, gw)
        assert gw.last["text"].startswith(f"Привет, Олег Первый! Ваш дом: {home.house.title}.")
        assert "menu:houses" in payloads(gw.last["buttons"])

    async def test_user_added_and_removed(self, home: Home, session: AsyncSession) -> None:
        gw = FakeGateway()
        newbie = {"user_id": 8_000_000 + next_id(), "name": "Светлана"}
        await handle({"update_type": "user_added", "chat_id": home.chat_id, "user": newbie}, gw)
        assert gw.last["text"].startswith("Добро пожаловать, Светлана!")
        assert payloads(gw.last["buttons"]) == ["menu:report"]
        user = await session.scalar(select(User).where(User.max_user_id == newbie["user_id"]))
        assert user is not None and await membership(user.id, home.house.id) is not None

        # житель ушёл из чата: доступ к дому закрывается, активный дом сбрасывается
        leaver = home.residents[1]
        async with get_sessionmaker()() as s:
            row = await s.get(User, leaver.id)
            assert row is not None
            row.active_house_id = home.house.id
            await s.commit()
        await handle({"update_type": "user_removed", "chat_id": home.chat_id, "user": max_user(leaver)}, gw)
        assert await membership(leaver.id, home.house.id) is None
        session.expire_all()
        assert (await session.get(User, leaver.id)).active_house_id is None  # type: ignore[union-attr]

    async def test_unknown_update_and_crash_are_swallowed(self, home: Home) -> None:
        class Broken(FakeGateway):
            async def send(self, **kwargs: Any) -> str | None:
                raise RuntimeError("MAX упал")

        await handlers.handle_update({"update_type": "chat_title_changed"}, FakeGateway())
        # ошибка в обработчике не роняет процесс бота
        await handlers.handle_update(message_update(home.admin, home.chat_id, "/start"), Broken())


class TestGroupCommands:
    async def test_help_app_and_menu(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[0]
        await handle(message_update(user, home.chat_id, "/start"), gw)
        assert gw.last["text"] == handlers.HELP_TEXT and gw.last["buttons"] == handlers.MENU
        await handle(message_update(user, home.chat_id, "/app"), gw)
        assert gw.last["text"] == "Приложение дома:"
        await handle(message_update(user, home.chat_id, "/меню@kuzya_bot"), gw)
        assert gw.last["text"] == f"🏠 {home.house.title}. Что сделать?"
        assert "menu:houses" not in payloads(gw.last["buttons"])
        await handle(message_update(user, home.chat_id, "/мои"), gw)
        assert gw.last["text"].startswith("Это личное")

    async def test_plain_chatter_gets_no_answer(self, home: Home) -> None:
        gw = FakeGateway()
        await handle(message_update(home.residents[0], home.chat_id, "Соседи, кто брал мой самокат?"), gw)
        await handle(message_update(home.residents[0], home.chat_id, "меню"), gw)
        assert gw.sent == []

    async def test_bot_and_empty_messages_are_ignored(self, home: Home) -> None:
        gw = FakeGateway()
        update = message_update(home.admin, home.chat_id, "Кузя, привет")
        update["message"]["sender"]["is_bot"] = True
        await handle(update, gw)
        await handle(message_update(home.admin, home.chat_id, "   "), gw)
        await handle({"update_type": "message_created", "message": {}}, gw)
        assert gw.sent == []

    async def test_message_in_new_chat_registers_house(self, session: AsyncSession) -> None:
        chat_id = -(3_000_000 + next_id())
        user = User(max_user_id=8_000_000 + next_id(), first_name="Новый", last_name="Житель")
        gw = FakeGateway(title="Новый чат дома", members=12)
        await handle(message_update(user, chat_id, "/start"), gw)
        house = await session.scalar(select(House).where(House.max_chat_id == chat_id))
        assert house is not None and house.title == "Новый чат дома"
        assert gw.last["text"] == handlers.HELP_TEXT


class TestModeration:
    async def test_rude_message_is_deleted_with_strikes(self, home: Home, session: AsyncSession) -> None:
        gw = FakeGateway()
        rude = home.residents[0]
        for n in range(1, 4):
            await handle(message_update(rude, home.chat_id, RUDE, mid=f"mid.rude{n}"), gw)
        assert gw.deleted == ["mid.rude1", "mid.rude2", "mid.rude3"]
        warnings = [m["text"] for m in gw.sent if m["chat_id"] == home.chat_id]
        assert "Предупреждение 1/3" in warnings[0] and "Сообщение удалено." in warnings[0]
        assert "Лимит предупреждений исчерпан" in warnings[2]
        (to_admin,) = [m for m in gw.sent if m["user_id"] == home.admin.max_user_id]
        assert to_admin["text"].startswith("🛡 Житель Олег Первый получил")
        member = await membership(rude.id, home.house.id)
        assert member is not None and member.strikes == 3
        logged = await session.scalar(
            select(func.count()).select_from(ModerationLog).where(ModerationLog.chat_id == home.chat_id)
        )
        assert logged == 3

    async def test_without_admin_rights_bot_says_so(self, home: Home) -> None:
        gw = FakeGateway(can_delete=False)
        await handle(message_update(home.residents[1], home.chat_id, RUDE), gw)
        assert "Удалить не смог: дайте мне права администратора." in gw.last["text"]


class TestProblemHints:
    async def test_hint_once_per_half_hour(self, home: Home) -> None:
        gw = FakeGateway()
        await handle(message_update(home.residents[0], home.chat_id, "У нас опять не работает лифт"), gw)
        assert gw.last["text"].startswith("Похоже на поломку (лифт)")
        assert payloads(gw.last["buttons"]) == ["menu:report"]
        await handle(message_update(home.residents[1], home.chat_id, "Во дворе сломали качели"), gw)
        assert len(gw.sent) == 1

    async def test_gas_advice_always(self, home: Home) -> None:
        gw = FakeGateway()
        for _ in range(2):
            await handle(message_update(home.residents[0], home.chat_id, "В подъезде пахнет газом"), gw)
        assert len(gw.sent) == 2
        assert all("104" in m["text"] for m in gw.sent)

    async def test_existing_issue_is_offered_for_vote(self, home: Home) -> None:
        async with get_sessionmaker()() as s:
            author = await s.get(User, home.residents[0].id)
            house = await s.get(House, home.house.id)
            assert author and house
            issue = await issues.create_issue(s, user=author, house=house, description="Течёт крыша над 9 этажом")
        gw = FakeGateway()
        await handle(message_update(home.residents[1], home.chat_id, "течёт крыша над 9 этажом, опять лужа"), gw)
        assert "уже есть заявка" in gw.last["text"]
        assert payloads(gw.last["buttons"])[0] == f"vote:{issue.id}"


class TestAgent:
    async def test_group_question_to_kuzya(self, home: Home) -> None:
        gw = FakeGateway()
        await handle(message_update(home.residents[0], home.chat_id, "Кузя, какие заявки открыты?"), gw)
        assert gw.last["text"].startswith("Олег, вот что я узнал")
        assert payloads(gw.last["buttons"]) == ["issues"]

    async def test_kuzya_creates_event_from_chat(self, home: Home, broker: FakeBroker, session: AsyncSession) -> None:
        gw = FakeGateway()
        await handle(message_update(home.admin, home.chat_id, "Кузя, создай субботник в субботу в 11 у площадки"), gw)
        ev = await session.scalar(select(Event).where(Event.house_id == home.house.id))
        assert ev is not None and ev.title == "Субботник во дворе" and ev.kind == "subbotnik"
        assert "готово! событие" in gw.last["text"].lower()
        assert payloads(gw.last["buttons"]) == ["events"]
        assert broker.sent(chat_id=home.chat_id)[0]["buttons"][0][0]["payload"] == f"join:{ev.id}"

    async def test_dm_vote_by_number_and_duplicate_issue(self, home: Home) -> None:
        gw = FakeGateway()
        olga, maria = home.residents[0], home.residents[1]
        created = await dm(gw, olga, "Не работает лифт в третьем подъезде")
        assert "заявка №" in created["text"] and payloads(created["buttons"]) == ["issues"]
        async with get_sessionmaker()() as s:
            issue_id = await s.scalar(select(Issue.id).where(Issue.house_id == home.house.id))
        dup = await dm(gw, maria, "Не работает лифт в третьем подъезде")
        assert "похожая заявка уже есть" in dup["text"].lower()
        voted = await dm(gw, maria, f"поддерживаю заявку {issue_id}")
        assert "голос учтён: 2 из 3" in voted["text"].lower()
        again = await dm(gw, maria, f"поддерживаю заявку {issue_id}")
        assert "вы уже поддержали эту заявку" in again["text"].lower()

    async def test_dm_profile_status_shelters_and_listings(self, home: Home) -> None:
        gw = FakeGateway()
        user = home.residents[2]
        assert "очков, уровень 1 «Новосёл»" in (await dm(gw, user, "сколько у меня очков?"))["text"]
        assert "Здоровье дома" in (await dm(gw, user, "Кузя, как дела у дома?"))["text"]
        shelters = await dm(gw, user, "Где ближайшее укрытие?")
        assert "Ближайшие укрытия" in shelters["text"] and payloads(shelters["buttons"]) == ["alert"]
        market = await dm(gw, user, "Кто что отдаёт даром?")
        assert "пока пусто" in market["text"] and payloads(market["buttons"]) == ["market"]

    async def test_dm_announcement_and_small_talk(self, home: Home, session: AsyncSession) -> None:
        gw = FakeGateway()
        made = await dm(gw, home.admin, "Кузя, сделай объявление: завтра с 10 до 12 не будет воды")
        assert "Объявление" in made["text"] and "(закрепил в чате)" in made["text"]
        item = await session.scalar(select(Announcement).where(Announcement.house_id == home.house.id))
        assert item is not None and item.pinned is True and item.title.startswith("Завтра с 10 до 12")
        assert (await dm(gw, home.admin, "Привет!"))["text"].startswith("Привет, Админ!")
        assert (await dm(gw, home.admin, "Спасибо тебе"))["text"].startswith("Всегда рад помочь")
        # длинный вопрос без явного намерения: Кузя ищет по заявкам, событиям и вещам дома
        found = await dm(gw, home.admin, "что там с водой у нас в доме")
        assert found["text"] == "Админ, вот что я узнал:\n\nПо этому запросу ничего не нашлось."

    async def test_dm_without_house(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(get_settings(), "pilot_house_fallback", False)
        stranger = User(max_user_id=8_000_000 + next_id(), first_name="Гость", last_name="")
        gw = FakeGateway()
        reply = await dm(gw, stranger, "Привет")
        assert reply["text"] == "Добавьте меня в чат вашего дома, и я начну помогать 🏠"

    async def test_dm_of_newcomer_goes_to_pilot_house(self, session: AsyncSession) -> None:
        # житель ещё не в чате с Кузей: личка показывает первый (пилотный) дом
        home = await make_home()
        stranger = User(max_user_id=8_000_000 + next_id(), first_name="Гость", last_name="")
        gw = FakeGateway()
        reply = await dm(gw, stranger, "Привет")
        assert reply["text"].startswith("Привет, Гость!")
        user = await session.scalar(select(User).where(User.max_user_id == stranger.max_user_id))
        first_house = await session.scalar(select(House.id).order_by(House.id).limit(1))
        assert user is not None and first_house != home.house.id
        assert await membership(user.id, first_house or 0) is not None

    async def test_channel_post_is_not_answered(self, home: Home) -> None:
        gw = FakeGateway()
        update = {
            "update_type": "message_created",
            "message": {"recipient": {"chat_id": -77, "chat_type": "channel"}, "body": {"text": "Новости"}},
        }
        await handle(update, gw)
        assert gw.sent == []
