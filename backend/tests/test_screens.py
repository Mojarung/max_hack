"""Экраны бота: правка на месте, один живой экран на чат, самоудаление в чате дома."""

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from domovoy.bot import screens

DM, GROUP = 1001, -2002


@dataclass
class Gw:
    fail_edit: bool = False
    sent: list[dict[str, Any]] = field(default_factory=list)
    edits: list[dict[str, Any]] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    async def send(self, *, text: str, chat_id: int | None = None, buttons: Any = None, photos: Any = None) -> str:
        mid = f"m{len(self.sent) + 1}"
        self.sent.append({"mid": mid, "chat_id": chat_id, "text": text, "photos": photos})
        return mid

    async def edit(self, *, mid: str, text: str | None, buttons: Any, media: Any = None) -> None:
        if self.fail_edit:
            raise RuntimeError("сообщение слишком старое")
        self.edits.append({"mid": mid, "text": text, "media": media})

    async def delete(self, *, mid: str) -> bool:
        self.deleted.append(mid)
        return True


async def show(gw: Gw, text: str, *, mid: str | None = None, chat_id: int = DM, **kw: Any) -> None:
    await screens.show(gw, chat_id=chat_id, is_group=chat_id == GROUP, mid=mid, text=text, buttons=[], **kw)  # type: ignore[arg-type]


async def test_button_on_screen_edits_it_in_place() -> None:
    gw = Gw()
    await show(gw, "меню")
    await show(gw, "заявки", mid="m1")
    assert [m["text"] for m in gw.sent] == ["меню"]
    assert gw.edits == [{"mid": "m1", "text": "заявки", "media": []}]


async def test_new_screen_removes_previous_one_in_same_chat_only() -> None:
    gw = Gw()
    await show(gw, "меню")
    await show(gw, "меню в чате дома", chat_id=GROUP)
    await show(gw, "меню ещё раз")
    assert gw.deleted == ["m1"]
    # кнопка на удалённом экране уже не правит его, а присылает новый
    await show(gw, "заявки", mid="m1")
    assert gw.sent[-1]["text"] == "заявки" and gw.deleted == ["m1", "m3"]


async def test_unknown_message_gets_a_new_screen() -> None:
    gw = Gw()
    await show(gw, "карточка", mid="уведомление-воркера")
    assert gw.edits == [] and gw.sent[0]["text"] == "карточка"


async def test_photos_need_a_new_message_and_back_drops_them() -> None:
    gw = Gw()
    await show(gw, "вещи")
    await show(gw, "дрель", mid="m1", photos=["listings/1.jpg"])
    assert gw.sent[-1]["photos"] == ["listings/1.jpg"] and gw.deleted == ["m1"]
    # экран с фото правкой без фото не станет: снова новое сообщение, старое убираем
    await show(gw, "вещи", mid="m2")
    assert gw.edits == [] and gw.deleted == ["m1", "m2"] and gw.sent[-1]["photos"] is None


async def test_in_place_edits_even_unknown_message() -> None:
    gw = Gw()
    await show(gw, "события: вы идёте", mid="старый-список", in_place=True)
    assert gw.sent == [] and gw.edits[0]["mid"] == "старый-список"
    await show(gw, "меню", mid="старый-список")
    assert gw.edits[-1]["text"] == "меню"


async def test_failed_edit_falls_back_to_new_message() -> None:
    gw = Gw()
    await show(gw, "меню")
    gw.fail_edit = True
    await show(gw, "заявки", mid="m1")
    assert gw.sent[-1]["text"] == "заявки" and gw.deleted == ["m1"]


async def test_group_screen_deletes_itself_after_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screens, "SCREEN_TTL_S", 0.05)
    gw = Gw()
    await show(gw, "меню", chat_id=GROUP)
    await show(gw, "личное меню")
    await asyncio.sleep(0.03)
    await show(gw, "заявки", mid="m1", chat_id=GROUP)  # нажатие продлевает жизнь экрана
    await asyncio.sleep(0.03)
    assert gw.deleted == []
    await asyncio.sleep(0.06)
    assert gw.deleted == ["m1"]
    # в личке экраны сами не пропадают
    assert "m2" in screens._screens and "m1" not in screens._screens


async def test_registry_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(screens, "MAX_SCREENS", 2)
    gw = Gw()
    for n in range(4):
        await show(gw, f"экран {n}", chat_id=DM + n)
    assert list(screens._screens) == ["m3", "m4"]
