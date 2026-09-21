from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.modules.misc_models import ModerationLog
from domovoy.modules.moderation.guardrails import ModerationResult


async def log_verdict(
    session: AsyncSession,
    *,
    source: str,
    text: str,
    verdict: ModerationResult,
    user_max_id: int | None = None,
    chat_id: int | None = None,
) -> None:
    """Пишем в журнал только срабатывания: чистые сообщения не храним (минимизация данных)."""
    if verdict.verdict == "ok":
        return
    session.add(
        ModerationLog(
            chat_id=chat_id,
            user_max_id=user_max_id,
            source=source,
            text=text[:2000],
            verdict=verdict.verdict,
            reasons=verdict.reasons,
        )
    )
