"""«Пульс дома»: состояние маскота Кузи считается из реальных данных дома.

Кузя - тамагочи всего дома. Открытые и просроченные заявки его огорчают, решённые проблемы,
события и помощь соседям радуют. Так маскот работает как понятный индикатор здоровья дома.
"""

from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.modules.events.models import Event
from domovoy.modules.issues.catalog import OPEN_STATUSES
from domovoy.modules.issues.models import Issue, IssueVote
from domovoy.modules.market.models import Listing
from domovoy.modules.misc_models import Alert
from domovoy.modules.users.models import Membership, User

Mood = Literal["happy", "ok", "worried", "sad", "alarm"]
HOUSE_LEVEL_XP = 400


class PulseStats(BaseModel):
    open_issues: int
    overdue_issues: int
    resolved_30d: int
    upcoming_events: int
    active_listings: int
    active_alert: bool
    # Личное: заявки в голосовании, которые житель ещё не поддержал (свои не считаем). Это цифра на вкладке
    awaiting_my_vote: int = 0


class PulseOut(BaseModel):
    mood: Mood
    score: int
    level: int
    xp: int
    xp_next: int
    phrase: str
    stats: PulseStats


def compute_score(s: PulseStats) -> int:
    score = 60
    score += 6 * min(s.resolved_30d, 5)
    score += 5 * min(s.upcoming_events, 3)
    score += min(s.active_listings, 5)
    score -= 5 * min(s.open_issues, 6)
    score -= 12 * min(s.overdue_issues, 3)
    return max(0, min(100, score))


def mood_for(score: int, alert: bool, overdue: int = 0) -> Mood:
    if alert:
        return "alarm"
    # просроченная заявка не даёт Кузе радоваться, даже если остальное в порядке
    if score >= 75 and overdue == 0:
        return "happy"
    if score >= 55:
        return "ok"
    if score >= 35:
        return "worried"
    return "sad"


def phrase_for(mood: Mood, s: PulseStats) -> str:
    if mood == "alarm":
        return "Тревога! Отойдите от окон и идите в укрытие, я покажу дорогу."
    if s.overdue_issues:
        return f"Просрочено заявок: {s.overdue_issues}. Готовлю жалобу в Госжилинспекцию."
    if mood == "happy":
        if s.upcoming_events:
            return "Дом в порядке, а скоро событие во дворе. Приходите, будет весело!"
        return "В доме тепло и спокойно. Спасибо, соседи!"
    if mood == "ok":
        return f"Открытых заявок: {s.open_issues}. Поддержите их голосом, и я отправлю обращения."
    if mood == "worried":
        return "Накопилось много заявок. Давайте вместе наберём голоса, остальное я оформлю сам."
    return "Мне грустно: дом давно без внимания. Сообщите о поломке или устройте субботник."


async def house_pulse(session: AsyncSession, house_id: int, user_id: int | None = None) -> PulseOut:
    now = datetime.now(UTC)

    async def count(stmt: object) -> int:
        return int(await session.scalar(stmt) or 0)  # type: ignore[call-overload]

    stats = PulseStats(
        open_issues=await count(
            select(func.count()).select_from(Issue).where(Issue.house_id == house_id, Issue.status.in_(OPEN_STATUSES))
        ),
        overdue_issues=await count(
            select(func.count())
            .select_from(Issue)
            .where(Issue.house_id == house_id, Issue.status.in_(("sent", "in_progress")), Issue.deadline_at < now)
        ),
        resolved_30d=await count(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.house_id == house_id, Issue.status == "resolved", Issue.resolved_at >= now - timedelta(days=30)
            )
        ),
        upcoming_events=await count(
            select(func.count()).select_from(Event).where(Event.house_id == house_id, Event.starts_at >= now)
        ),
        active_listings=await count(
            select(func.count()).select_from(Listing).where(Listing.house_id == house_id, Listing.status == "active")
        ),
        awaiting_my_vote=await count(
            select(func.count())
            .select_from(Issue)
            .where(
                Issue.house_id == house_id,
                Issue.status == "voting",
                Issue.author_id != user_id,
                ~exists().where(IssueVote.issue_id == Issue.id, IssueVote.user_id == user_id),
            )
        )
        if user_id is not None
        else 0,
        active_alert=bool(
            await count(
                select(func.count())
                .select_from(Alert)
                .where(Alert.active.is_(True), (Alert.house_id == house_id) | Alert.house_id.is_(None))
            )
        ),
    )
    xp = await count(
        select(func.coalesce(func.sum(User.points), 0))
        .select_from(User)
        .join(Membership, Membership.user_id == User.id)
        .where(Membership.house_id == house_id)
    )
    level = xp // HOUSE_LEVEL_XP + 1
    score = compute_score(stats)
    mood = mood_for(score, stats.active_alert, stats.overdue_issues)
    return PulseOut(
        mood=mood,
        score=score,
        level=level,
        xp=xp,
        xp_next=level * HOUSE_LEVEL_XP,
        phrase=phrase_for(mood, stats),
        stats=stats,
    )
