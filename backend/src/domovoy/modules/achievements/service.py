"""Начисление очков и выдача ачивок.

Каждое полезное действие пишется в points_log с причиной `action`. Счётчики ачивок
считаются по этому журналу, поэтому отдельные таблицы прогресса не нужны.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.modules.achievements.catalog import ACHIEVEMENTS, ACTION_POINTS, AchievementDef
from domovoy.modules.misc_models import UserAchievement
from domovoy.modules.users.models import PointsLog, User


async def record_action(session: AsyncSession, user: User, house_id: int | None, action: str) -> list[AchievementDef]:
    """Начисляет очки за действие и возвращает новые ачивки. Коммит делает вызывающий код."""
    points = ACTION_POINTS.get(action, 0)
    session.add(PointsLog(user_id=user.id, house_id=house_id, delta=points, reason=action))
    user.points += points
    await session.flush()

    count = await session.scalar(
        select(func.count()).select_from(PointsLog).where(PointsLog.user_id == user.id, PointsLog.reason == action)
    )
    earned = set(await session.scalars(select(UserAchievement.code).where(UserAchievement.user_id == user.id)))
    awarded: list[AchievementDef] = []
    for ach in ACHIEVEMENTS:
        if ach.action == action and ach.code not in earned and (count or 0) >= ach.threshold:
            session.add(UserAchievement(user_id=user.id, code=ach.code))
            session.add(PointsLog(user_id=user.id, house_id=house_id, delta=ach.points, reason=f"ach:{ach.code}"))
            user.points += ach.points
            awarded.append(ach)
    return awarded


async def revoke_action(session: AsyncSession, user: User, action: str) -> None:
    """Откат действия (например, снятый голос): убираем последнюю запись и очки."""
    last_id = await session.scalar(
        select(PointsLog.id)
        .where(PointsLog.user_id == user.id, PointsLog.reason == action)
        .order_by(PointsLog.id.desc())
        .limit(1)
    )
    if last_id is None:
        return
    await session.execute(delete(PointsLog).where(PointsLog.id == last_id))
    user.points = max(0, user.points - ACTION_POINTS.get(action, 0))


async def announce(house_id: int | None, user: User, awarded: list[AchievementDef]) -> None:
    for ach in awarded:
        await bus.emit(
            house_id,
            "achievement.awarded",
            {"user_id": user.id, "code": ach.code, "title": ach.title, "icon": ach.icon, "points": ach.points},
        )
