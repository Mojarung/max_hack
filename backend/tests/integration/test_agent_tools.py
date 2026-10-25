"""Инструменты агента Кузи напрямую: те же права и проверки, что у REST API, ответы для чата."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fakes import FakeBroker
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.agent.tools import AgentContext, build_tools
from domovoy.core.db import get_sessionmaker
from domovoy.core.embeddings import embed
from domovoy.modules.events.models import Event
from domovoy.modules.market.models import Listing
from domovoy.modules.misc_models import Alert, Announcement
from integration.helpers import Home

pytestmark = pytest.mark.integration


def tools_for(home: Home, user_index: int = -1, *, admin: bool = False) -> dict[str, Any]:
    user = home.admin if user_index < 0 else home.residents[user_index]
    return {t.name: t for t in build_tools(AgentContext(user_id=user.id, house_id=home.house.id, is_admin=admin))}


class TestIssuesTools:
    async def test_list_vote_and_threshold(self, home: Home, broker: FakeBroker) -> None:
        olga = tools_for(home, 0)
        assert await olga["list_issues"].ainvoke({}) == "Открытых заявок нет. Дом в порядке!"
        created = await olga["create_issue"].ainvoke({"description": "Сломаны качели на детской площадке"})
        assert created.startswith("Заявка №") and "Нужно 3 голосов" in created
        issue_id = int(created.split("№")[1].split()[0])

        listed = await tools_for(home, 1)["list_issues"].ainvoke({"status": "all"})
        assert f"№{issue_id}" in listed and "голосов 1/3" in listed
        assert await tools_for(home, 1)["vote_issue"].ainvoke({"issue_id": issue_id}) == "Голос учтён: 2 из 3."
        reached = await tools_for(home, 2)["vote_issue"].ainvoke({"issue_id": issue_id})
        assert reached.startswith("Голос учтён, и голосов теперь хватает")
        assert await tools_for(home, 2)["vote_issue"].ainvoke({"issue_id": 999999}) == "Заявка не найдена"

    async def test_unknown_house_is_reported(self, home: Home) -> None:
        tools = {t.name: t for t in build_tools(AgentContext(user_id=home.admin.id, house_id=10**8))}
        with pytest.raises(HTTPException) as err:
            await tools["my_profile"].ainvoke({})
        assert (err.value.status_code, err.value.detail) == (404, "Не нашёл ваш дом")


class TestEventsAndAnnouncements:
    async def test_create_event_checks_date(self, home: Home) -> None:
        tools = tools_for(home)
        assert (await tools["create_event"].ainvoke({"title": "Субботник", "when": "когда-нибудь"})).startswith(
            "Не понял дату"
        )
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        assert await tools["create_event"].ainvoke({"title": "Субботник", "when": past}) == (
            "Дата события уже прошла, выберите будущую"
        )
        done = await tools["create_event"].ainvoke(
            {"title": "Турнир по футболу", "when": "завтра в 18:30", "place": "Коробка", "kind": "unknown"}
        )
        assert done.startswith("Готово! Событие №") and "Коробка" in done
        listed = await tools_for(home, 0)["list_events"].ainvoke({})
        assert "«Турнир по футболу»" in listed and "идут 1" in listed
        assert "(вы записаны)" in await tools["list_events"].ainvoke({})

    async def test_announcement_with_date_creates_event(
        self, home: Home, broker: FakeBroker, session: AsyncSession
    ) -> None:
        tools = tools_for(home, admin=True)
        reply = await tools["create_announcement"].ainvoke(
            {"title": "Субботник во дворе", "when": "в субботу в 11", "place": "У площадки"}
        )
        assert "событие №" in reply and "(закрепил в чате)" in reply
        item = await session.scalar(select(Announcement).where(Announcement.house_id == home.house.id))
        assert item is not None and item.event_id is not None and item.pinned is True
        assert item.text.startswith("Приглашаем всех соседей!")
        ev = await session.get(Event, item.event_id)
        assert ev is not None and ev.kind == "subbotnik" and ev.place == "У площадки"
        # у события свой анонс с кнопкой «Иду»: второго сообщения объявления нет, событие закреплено
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert msg["pin"] is True and msg["buttons"][0][0]["payload"] == f"join:{ev.id}"

    async def test_rude_announcement_is_refused(self, home: Home) -> None:
        reply = await tools_for(home, 0)["create_announcement"].ainvoke({"title": "Внимание", "text": "Ты дурак, блин"})
        assert reply.startswith("Кузя не пропустил объявление")


class TestOtherTools:
    async def test_listings_shelters_profile_and_search(self, home: Home, session: AsyncSession) -> None:
        session.add_all(
            [
                Listing(
                    house_id=home.house.id,
                    author_id=home.admin.id,
                    title="Детская коляска",
                    description="Прогулочная",
                    price=0,
                    embedding=embed("Детская коляска Прогулочная"),
                ),
                Listing(house_id=home.house.id, author_id=home.admin.id, title="Шкаф-купе", description="", price=3000),
            ]
        )
        session.add(Alert(house_id=home.house.id, kind="drone", message="Тревога"))
        await session.commit()
        tools = tools_for(home, 0)

        market = await tools["list_listings"].ainvoke({})
        assert "«Детская коляска» - даром" in market and "«Шкаф-купе» - 3000 ₽" in market
        assert (await tools["list_listings"].ainvoke({"query": "коляска"})).count("№") == 1
        shelters = await tools["nearest_shelters"].ainvoke({})
        assert shelters.startswith("Сейчас действует тревога! Ближайшие укрытия:")
        assert "Маршрут в Яндекс Картах: https://yandex.ru/maps/" in shelters
        assert "до следующего уровня 50 очков" in await tools["my_profile"].ainvoke({})
        found = await tools["search_house"].ainvoke({"query": "детская коляска"})
        assert found.startswith("Нашёл:") and "Объявление №" in found
        assert await tools["search_house"].ainvoke({"query": "zzzzqqq"}) == "По этому запросу ничего не нашлось."
        status = await tools["house_status"].ainvoke({})
        assert status.startswith("Здоровье дома") and "объявлений в «Вещах соседей»: 2" in status

    async def test_legend_has_no_next_level(self, home: Home) -> None:
        async with get_sessionmaker()() as s:
            from domovoy.modules.users.models import User

            user = await s.get(User, home.residents[2].id)
            assert user is not None
            user.points = 5000
            await s.commit()
        profile = await tools_for(home, 2)["my_profile"].ainvoke({})
        assert profile.startswith("У вас 5000 очков, уровень 8 «Легенда дома»") and "следующего" not in profile
