"""Бизнес-логика заявок. Используется REST API, ботом и инструментами агента."""

from datetime import UTC, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core import bus
from domovoy.core.db import lock_row
from domovoy.core.embeddings import embed
from domovoy.modules.achievements import service as achievements
from domovoy.modules.issues.catalog import OPEN_STATUSES, STATUS_TITLES, category
from domovoy.modules.issues.classifier import classify
from domovoy.modules.issues.models import Issue, IssueUpdate, IssueVote
from domovoy.modules.issues.schemas import IssueOut, issue_out
from domovoy.modules.search.hybrid import hybrid_search
from domovoy.modules.users.models import House, Organization, User
from domovoy.modules.users.service import votes_needed

EMERGENCY_CATEGORIES = {"gas"}


def app_button(text: str, payload: str) -> dict[str, str]:
    return {"type": "open_app", "text": text, "payload": payload}


def vote_buttons(issue: Issue) -> list[list[dict[str, str]]]:
    return [
        [
            {
                "type": "callback",
                "text": f"👍 Поддерживаю ({issue.votes_count}/{issue.votes_needed})",
                "payload": f"vote:{issue.id}",
            }
        ],
        [app_button("Подробнее", f"issue_{issue.id}")],
    ]


def issue_chat_text(issue: Issue) -> str:
    """Текст сообщения заявки в чате дома. Им же бот обновляет сообщение после каждого голоса."""
    org = issue.responsible_org.name if issue.responsible_org else "исполнителю"
    head = f"🏠 Проблема: **{issue.title}**\n{issue.author.full_name}: {issue.description[:300]}"
    if issue.status == "voting":
        left = max(issue.votes_needed - issue.votes_count, 0)
        return (
            f"{head}\n\nПоддержали {issue.votes_count} из {issue.votes_needed}, нужно ещё {left}. "
            f"Когда голосов хватит, я сам отправлю обращение: {org}."
        )
    if issue.status in ("resolved", "rejected"):
        return f"{head}\n\n{STATUS_TITLES.get(issue.status, issue.status)}. Спасибо всем, кто поддержал!"
    return f"{head}\n\n✅ Голоса собраны ({issue.votes_count}). Обращение отправлено: {org}. Слежу за сроком."


async def responsible_org(session: AsyncSession, house: House, org_kind: str) -> Organization | None:
    if org_kind == "uk" and house.uk_org_id:
        return await session.get(Organization, house.uk_org_id)
    return await session.scalar(select(Organization).where(Organization.kind == org_kind).limit(1))


def status_buttons(issue: Issue) -> list[list[dict[str, str]]]:
    return [[app_button("Статус заявки", f"issue_{issue.id}")]]


def chat_buttons(issue: Issue) -> list[list[dict[str, str]]]:
    return vote_buttons(issue) if issue.status == "voting" else status_buttons(issue)


async def refresh_chat_message(issue: Issue) -> None:
    """Счётчик голосов в сообщении заявки в чате должен совпадать с приложением."""
    if issue.chat_message_id and issue.house.max_chat_id:
        await bus.publish("bot.issue_refresh", {"issue_id": issue.id})


async def get_issue(session: AsyncSession, issue_id: int, house_id: int) -> Issue:
    issue = await session.get(Issue, issue_id)
    if issue is None or issue.house_id != house_id:
        raise HTTPException(404, "Заявка не найдена")
    return issue


async def has_voted(session: AsyncSession, issue_id: int, user_id: int) -> bool:
    return (await session.get(IssueVote, (issue_id, user_id))) is not None


async def timeline(session: AsyncSession, issue_id: int) -> list[IssueUpdate]:
    return list(
        await session.scalars(select(IssueUpdate).where(IssueUpdate.issue_id == issue_id).order_by(IssueUpdate.id))
    )


async def create_issue(
    session: AsyncSession,
    *,
    user: User,
    house: House,
    description: str,
    title: str | None = None,
    location_hint: str | None = None,
    photos: list[str] | None = None,
) -> Issue:
    description = description.strip()
    if len(description) < 5:
        raise HTTPException(422, "Опишите проблему хотя бы парой слов")
    result = await classify(description if not title else f"{title}. {description}")
    cat = category(result.category)
    org = await responsible_org(session, house, cat.org_kind)
    issue = Issue(
        house_id=house.id,
        author_id=user.id,
        title=(title or result.title).strip()[:200],
        description=description[:4000],
        location_hint=(location_hint or None),
        category=cat.code,
        classifier_source=result.source,
        classifier_confidence=result.confidence,
        photos=photos or [],
        votes_count=1,
        votes_needed=votes_needed(house),
        responsible_org_id=org.id if org else None,
        legal_basis=cat.legal_basis,
        deadline_hours=cat.deadline_hours,
        embedding=embed(f"{title or ''} {description} {location_hint or ''}"),
    )
    session.add(issue)
    await session.flush()
    session.add(IssueVote(issue_id=issue.id, user_id=user.id))
    session.add(IssueUpdate(issue_id=issue.id, status="voting", note=f"Заявку создал(а) {user.full_name}"))
    awarded = await achievements.record_action(session, user, house.id, "issue_created")
    emergency = cat.code in EMERGENCY_CATEGORIES
    if emergency or issue.votes_count >= issue.votes_needed:
        _mark_sent(
            session, issue, "Экстренная категория: отправлено без голосования" if emergency else "Порог голосов набран"
        )
    await session.commit()
    await session.refresh(issue)

    await achievements.announce(house.id, user, awarded)
    await bus.emit(house.id, "issue.created", issue_out(issue, True).model_dump(mode="json"))
    await bus.emit(house.id, "pulse.changed", {})
    if house.max_chat_id:
        if emergency:
            await bus.bot_send(
                chat_id=house.max_chat_id,
                text=(
                    f"🚨 **{issue.title}**\n{user.full_name} сообщает о запахе газа. "
                    "Не пользуйтесь огнём и выключателями, откройте окна и звоните **104** или **112**. "
                    "Я уже передал заявку в аварийную газовую службу."
                ),
            )
        else:
            await bus.bot_send(
                chat_id=house.max_chat_id,
                text=issue_chat_text(issue),
                buttons=vote_buttons(issue) if issue.status == "voting" else status_buttons(issue),
                photos=issue.photos,
                ref={"issue_id": issue.id},
            )
    if issue.status == "sent":
        await bus.publish("issue.dispatch", {"issue_id": issue.id})
    return issue


def _mark_sent(session: AsyncSession, issue: Issue, note: str) -> None:
    now = datetime.now(UTC)
    issue.status = "sent"
    issue.sent_at = now
    issue.deadline_at = now + timedelta(hours=issue.deadline_hours)
    session.add(IssueUpdate(issue_id=issue.id, status="sent", note=note))


async def vote(session: AsyncSession, issue: Issue, user: User, *, from_chat: bool = False) -> tuple[Issue, bool]:
    """Голос за заявку. Возвращает заявку и признак «порог только что набран».

    Строка заявки блокируется (SELECT ... FOR UPDATE), поэтому одновременные голоса соседей
    не теряются, а переход через порог происходит ровно один раз.
    """
    await lock_row(session, Issue, issue.id)
    await session.refresh(issue)
    if issue.status != "voting":
        raise HTTPException(409, "Голосование по этой заявке уже закрыто")
    if await has_voted(session, issue.id, user.id):
        raise HTTPException(409, "Вы уже поддержали эту заявку")
    session.add(IssueVote(issue_id=issue.id, user_id=user.id))
    issue.votes_count += 1
    awarded = await achievements.record_action(session, user, issue.house_id, "issue_voted")
    reached = issue.votes_count >= issue.votes_needed
    author_awarded = []
    if reached:
        _mark_sent(session, issue, f"Порог набран: {issue.votes_count} из {issue.votes_needed} голосов")
        author = await session.get(User, issue.author_id)
        if author:
            author_awarded = await achievements.record_action(session, author, issue.house_id, "issue_sent")
    await session.commit()
    await session.refresh(issue)

    await achievements.announce(issue.house_id, user, awarded)
    if reached and author_awarded:
        await achievements.announce(issue.house_id, issue.author, author_awarded)
    await bus.emit(issue.house_id, "issue.updated", issue_out(issue, False).model_dump(mode="json"))
    if not from_chat:
        # голос из приложения или от агента: обновляем кнопку «Поддерживаю (N/M)» в чате
        await refresh_chat_message(issue)
    if reached:
        await bus.publish("issue.dispatch", {"issue_id": issue.id})
        await bus.emit(issue.house_id, "pulse.changed", {})
    return issue, reached


async def unvote(session: AsyncSession, issue: Issue, user: User) -> Issue:
    await lock_row(session, Issue, issue.id)
    await session.refresh(issue)
    if issue.status != "voting":
        raise HTTPException(409, "Голосование уже закрыто, голос отозвать нельзя")
    if issue.author_id == user.id:
        raise HTTPException(409, "Автор заявки не может отозвать свой голос")
    vote_row = await session.get(IssueVote, (issue.id, user.id))
    if vote_row is None:
        raise HTTPException(409, "Вы ещё не голосовали за эту заявку")
    await session.delete(vote_row)
    issue.votes_count = max(0, issue.votes_count - 1)
    await achievements.revoke_action(session, user, "issue_voted")
    await session.commit()
    await session.refresh(issue)
    await bus.emit(issue.house_id, "issue.updated", issue_out(issue, False).model_dump(mode="json"))
    await refresh_chat_message(issue)
    return issue


async def set_status(session: AsyncSession, issue: Issue, user: User, is_admin: bool, status: str, note: str) -> Issue:
    if not (is_admin or issue.author_id == user.id):
        raise HTTPException(403, "Менять статус может автор заявки или администратор дома")
    if issue.status in ("resolved", "rejected"):
        raise HTTPException(409, "Заявка уже закрыта")
    issue.status = status
    if status == "resolved":
        issue.resolved_at = datetime.now(UTC)
    session.add(
        IssueUpdate(issue_id=issue.id, status=status, note=note or f"{STATUS_TITLES[status]} ({user.full_name})")
    )
    awarded = []
    if status == "resolved":
        author = await session.get(User, issue.author_id)
        if author:
            awarded = await achievements.record_action(session, author, issue.house_id, "issue_resolved")
    await session.commit()
    await session.refresh(issue)
    await achievements.announce(issue.house_id, issue.author, awarded)
    await bus.emit(issue.house_id, "issue.updated", issue_out(issue, False).model_dump(mode="json"))
    await bus.emit(issue.house_id, "pulse.changed", {})
    await refresh_chat_message(issue)
    if status == "resolved" and issue.house.max_chat_id:
        await bus.bot_send(
            chat_id=issue.house.max_chat_id,
            text=f"🎉 Проблема решена: **{issue.title}**. Спасибо всем, кто голосовал! Кузя доволен.",
        )
    return issue


async def list_issues(
    session: AsyncSession, house_id: int, user_id: int, status: str | None = None, q: str | None = None, limit: int = 50
) -> list[IssueOut]:
    where = [Issue.house_id == house_id]
    if status == "open":
        where.append(Issue.status.in_(OPEN_STATUSES))
    elif status:
        where.append(Issue.status == status)
    if q:
        found = await hybrid_search(session, Issue, q, where=where, limit=limit)
        pairs: list[tuple[Issue, float | None]] = [(i, s) for i, s in found]
    else:
        rows = await session.scalars(select(Issue).where(*where).order_by(Issue.created_at.desc()).limit(limit))
        pairs = [(i, None) for i in rows]
    voted = set(
        await session.scalars(
            select(IssueVote.issue_id).where(
                IssueVote.user_id == user_id, IssueVote.issue_id.in_([i.id for i, _ in pairs])
            )
        )
    )
    return [issue_out(i, i.id in voted, s) for i, s in pairs]


async def similar_issues(session: AsyncSession, house_id: int, user_id: int, text: str) -> list[IssueOut]:
    """Поиск дублей среди открытых заявок: житель поддержит существующую вместо новой."""
    found = await hybrid_search(
        session,
        Issue,
        text,
        where=[Issue.house_id == house_id, Issue.status.in_(OPEN_STATUSES)],
        limit=3,
        min_score=0.35,
    )
    voted = set(await session.scalars(select(IssueVote.issue_id).where(IssueVote.user_id == user_id)))
    return [issue_out(i, i.id in voted, s) for i, s in found]
