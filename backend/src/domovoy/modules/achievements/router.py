from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from domovoy.api.deps import CtxDep, SessionDep
from domovoy.modules.achievements.catalog import ACHIEVEMENTS, level_for
from domovoy.modules.common_schemas import UserShort
from domovoy.modules.misc_models import UserAchievement
from domovoy.modules.users.models import Membership, User

router = APIRouter(prefix="/achievements", tags=["Ачивки"])


class AchievementOut(BaseModel):
    code: str
    title: str
    description: str
    icon: str
    points: int
    earned: bool
    awarded_at: datetime | None


class LeaderRow(BaseModel):
    rank: int
    user: UserShort
    points: int
    level_title: str
    is_me: bool


class AchievementsOut(BaseModel):
    items: list[AchievementOut]
    leaderboard: list[LeaderRow]


@router.get("", response_model=AchievementsOut)
async def achievements(session: SessionDep, ctx: CtxDep) -> AchievementsOut:
    earned = {
        a.code: a.created_at
        for a in await session.scalars(select(UserAchievement).where(UserAchievement.user_id == ctx.user.id))
    }
    items = [
        AchievementOut(
            code=a.code,
            title=a.title,
            description=a.description,
            icon=a.icon,
            points=a.points,
            earned=a.code in earned,
            awarded_at=earned.get(a.code),
        )
        for a in ACHIEVEMENTS
    ]
    top = await session.scalars(
        select(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.house_id == ctx.house.id)
        .order_by(User.points.desc(), User.id)
        .limit(20)
    )
    leaderboard = [
        LeaderRow(
            rank=i + 1,
            user=UserShort.of(u),
            points=u.points,
            level_title=level_for(u.points)[1],
            is_me=u.id == ctx.user.id,
        )
        for i, u in enumerate(top)
    ]
    return AchievementsOut(items=items, leaderboard=leaderboard)
