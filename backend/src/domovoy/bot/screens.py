"""Экраны бота: меню, списки и карточки, которые меняются на месте.

Как в ботах Telegram: нажатие кнопки на экране меняет его, а не присылает новое сообщение.
Новый экран в том же чате убирает прежний, а в чате дома экран сам удаляется через 10 минут
без нажатий, чтобы меню и списки не засоряли общий чат. Реестр живёт в памяти процесса бота:
после перезапуска старые экраны остаются в чате, и кнопка на них просто пришлёт новый.
"""

import asyncio
import time
from dataclasses import dataclass, field

import structlog

from domovoy.bot.gateway import Buttons, Gateway

log = structlog.get_logger(__name__)

SCREEN_TTL_S = 10 * 60
MAX_SCREENS = 2000


@dataclass
class Screen:
    chat_id: int
    is_group: bool
    photos: bool
    touched: float = field(default_factory=time.monotonic)


# MAX id сообщения -> экран; чат -> последний экран в нём
_screens: dict[str, Screen] = {}
_live: dict[int, str] = {}
_expiry: set[asyncio.Task[None]] = set()


async def show(
    gw: Gateway,
    *,
    chat_id: int,
    is_group: bool,
    mid: str | None,
    text: str,
    buttons: Buttons,
    photos: list[str] | None = None,
    in_place: bool = False,
) -> None:
    """Показывает экран вместо нажатого, а если его нельзя изменить, присылает новый и убирает прежний.

    in_place: нажатое сообщение и есть этот экран (список событий после «Иду», карточка после голоса),
    его меняем, даже если бот перезапускался и реестр о нём не знает.
    """
    screen = _screens.get(mid) if mid else None
    editable = in_place or (screen is not None and screen.chat_id == chat_id and not screen.photos)
    if mid and editable and not photos:
        try:
            # пустой список вложений: фото с прежнего экрана (объявления, черновика) не остаются
            await gw.edit(mid=mid, text=text, buttons=buttons, media=[])
        except Exception:
            log.warning("chat.screen_edit_failed", mid=mid, exc_info=True)
        else:
            _remember(gw, mid, chat_id=chat_id, is_group=is_group, photos=False)
            return
    new_mid = await gw.send(chat_id=chat_id, text=text, buttons=buttons, photos=photos or None)
    old = _live.get(chat_id)
    if old and old != new_mid:
        _forget(old)
        await gw.delete(mid=old)
    if new_mid:
        _remember(gw, new_mid, chat_id=chat_id, is_group=is_group, photos=bool(photos))


def known(mid: str) -> bool:
    """Это сообщение - живой экран, его можно править на месте."""
    return mid in _screens


def _remember(gw: Gateway, mid: str, *, chat_id: int, is_group: bool, photos: bool) -> None:
    screen = _screens.get(mid)
    if screen is None:
        _screens[mid] = Screen(chat_id=chat_id, is_group=is_group, photos=photos)
        if is_group:
            task = asyncio.create_task(_expire(gw, mid))
            _expiry.add(task)
            task.add_done_callback(_expiry.discard)
    else:
        screen.photos = photos
        screen.touched = time.monotonic()
    _live[chat_id] = mid
    for stale in list(_screens)[: max(0, len(_screens) - MAX_SCREENS)]:
        _forget(stale)


def _forget(mid: str) -> None:
    screen = _screens.pop(mid, None)
    if screen is not None and _live.get(screen.chat_id) == mid:
        _live.pop(screen.chat_id, None)


async def _expire(gw: Gateway, mid: str) -> None:
    """Экран в чате дома удаляется сам, когда к нему 10 минут никто не притрагивался."""
    while (screen := _screens.get(mid)) is not None:
        left = screen.touched + SCREEN_TTL_S - time.monotonic()
        if left > 0:
            await asyncio.sleep(left)
            continue
        _forget(mid)
        try:
            await gw.delete(mid=mid)
        except Exception:
            log.warning("chat.screen_expire_failed", mid=mid, exc_info=True)
        return


def reset() -> None:
    """Забыть все экраны и остановить таймеры (для тестов)."""
    for task in list(_expiry):
        task.cancel()
    _expiry.clear()
    _screens.clear()
    _live.clear()
