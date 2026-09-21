"""Текст официального обращения и жалобы в жилинспекцию.

Каркас документа (реквизиты, основание, срок) собирается из справочника детерминированно.
LLM, если подключена, только переписывает описание проблемы в деловом стиле.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import structlog

from domovoy.agent.llm import get_llm, is_real_llm
from domovoy.modules.issues.catalog import category
from domovoy.modules.issues.models import Issue

log = structlog.get_logger(__name__)
MSK = ZoneInfo("Europe/Moscow")

REWRITE_PROMPT = """Перепиши жалобу жителя в деловом стиле для официального обращения в управляющую организацию.
Только факты из текста, 2-4 предложения, без приветствий и подписи, без выдуманных деталей.
Текст жителя: «{text}»"""


async def business_description(issue: Issue) -> str:
    raw = f"{issue.title}. {issue.description}"
    if not is_real_llm():
        return raw
    try:
        result = await get_llm().ainvoke(REWRITE_PROMPT.format(text=raw[:2000]))
        text = str(result.content).strip()
        return text or raw
    except Exception:
        log.warning("appeal.llm_failed", exc_info=True)
        return raw


def _fmt(dt: datetime | None) -> str:
    return dt.astimezone(MSK).strftime("%d.%m.%Y %H:%M") if dt else "-"


def render_appeal(issue: Issue, description: str) -> str:
    cat = category(issue.category)
    org = issue.responsible_org.name if issue.responsible_org else "Ответственная организация"
    house = issue.house
    return (
        f"Кому: {org}\n"
        f"От: собственники и жители МКД по адресу {house.address} "
        f"(коллективное обращение, поддержали {issue.votes_count} жителей)\n"
        f"Канал: MAX, в соответствии с порядком информационного взаимодействия с 01.09.2026\n\n"
        f"ОБРАЩЕНИЕ № {issue.id} от {_fmt(issue.sent_at)}\n"
        f"Категория: {cat.title}\n"
        f"Место: {issue.location_hint or 'общее имущество МКД'}\n\n"
        f"{description}\n\n"
        f"Прошу устранить неисправность и сообщить о результате. "
        f"Основание (справочно): {cat.legal_basis}\n"
        f"Нормативный срок: {cat.deadline_hours} ч, до {_fmt(issue.deadline_at)} (МСК).\n"
        f"Фотофиксация: {len(issue.photos or [])} фото приложено в карточке заявки.\n\n"
        f"Сформировано сервисом «Домовой Кузя». Статус обращения отслеживается жителями в MAX."
    )


def render_escalation(issue: Issue) -> str:
    return (
        "Кому: Государственная жилищная инспекция Республики Татарстан\n"
        f"Жалоба на неисполнение обращения № {issue.id} от {_fmt(issue.sent_at)}.\n"
        f"Исполнитель: {issue.responsible_org.name if issue.responsible_org else '-'}. "
        f"Нормативный срок истёк {_fmt(issue.deadline_at)} (МСК), проблема «{issue.title}» не устранена.\n"
        "Прошу провести проверку и обязать исполнителя устранить нарушение."
    )
