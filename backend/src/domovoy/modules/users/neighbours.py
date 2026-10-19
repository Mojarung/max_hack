"""Действия с соседом из его профиля: поблагодарить и написать через Кузю.

Благодарность - запись в журнале очков с причиной «thanks:<id того, кто благодарит>»:
отдельная таблица не нужна, по журналу же считаются ограничение «раз в сутки» и счётчик.
"""

import time
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.core.db import lock_row, utcnow
from domovoy.modules.users.models import PointsLog, User

THANKS_POINTS = 5
THANKS_PREFIX = "thanks:"
THANKS_COOLDOWN = timedelta(hours=24)
# Между двумя сообщениями одному и тому же соседу: защита от спама через бота
MESSAGE_COOLDOWN_S = 60
_last_message: dict[tuple[int, int], float] = {}


async def thanks_count(session: AsyncSession, user: User) -> int:
    stmt = (
        select(func.count())
        .select_from(PointsLog)
        .where(PointsLog.user_id == user.id, PointsLog.reason.startswith(THANKS_PREFIX))
    )
    return int(await session.scalar(stmt) or 0)


async def thanked_recently(session: AsyncSession, giver: User, target: User) -> bool:
    since = utcnow() - THANKS_COOLDOWN
    stmt = (
        select(func.count())
        .select_from(PointsLog)
        .where(
            PointsLog.user_id == target.id,
            PointsLog.reason == f"{THANKS_PREFIX}{giver.id}",
            PointsLog.created_at >= since,
        )
    )
    return bool(await session.scalar(stmt))


async def thank(session: AsyncSession, giver: User, target: User, house_id: int) -> None:
    """+5 очков соседу от имени жителя, не чаще раза в сутки. Коммит делает вызывающий код."""
    if giver.id == target.id:
        raise HTTPException(409, "Себя поблагодарить нельзя")
    # строка соседа под блокировкой: два одновременных «спасибо» не начислят дважды
    await lock_row(session, User, target.id)
    await session.refresh(target)
    if await thanked_recently(session, giver, target):
        raise HTTPException(409, "Вы уже благодарили этого соседа сегодня")
    session.add(
        PointsLog(user_id=target.id, house_id=house_id, delta=THANKS_POINTS, reason=f"{THANKS_PREFIX}{giver.id}")
    )
    target.points += THANKS_POINTS
    await session.flush()


async def notify_thanks(giver: User, target: User) -> None:
    """Сообщение соседу - после коммита, чтобы он не узнал о +5, которых нет."""
    await bus.bot_send(
        user_id=target.max_user_id,
        text=f"🙏 {who(giver)} говорит вам спасибо за помощь дому. +{THANKS_POINTS} очков.",
    )


async def send_message(sender: User, target: User, text: str) -> None:
    """Пересылает сообщение соседу в личку от Кузи: MAX id и телефоны жителей друг другу не видны."""
    if sender.id == target.id:
        raise HTTPException(409, "Это ваш профиль")
    key = (sender.id, target.id)
    now = time.monotonic()
    if now - _last_message.get(key, -MESSAGE_COOLDOWN_S) < MESSAGE_COOLDOWN_S:
        raise HTTPException(429, "Сообщение уже отправлено, подождите минуту")
    contact = f" (@{sender.username})" if sender.username else ""
    await bus.bot_send(
        user_id=target.max_user_id,
        text=(
            f"✉️ {who(sender)}{contact} пишет вам через Кузю:\n\n{text.strip()}"
            "\n\nОтветьте соседу в личных сообщениях MAX."
        ),
    )
    # метку ставим после отправки: при сбое житель сможет сразу повторить
    _last_message[key] = now


def who(user: User) -> str:
    return user.full_name + (f", кв. {user.apartment}" if user.apartment else "")
