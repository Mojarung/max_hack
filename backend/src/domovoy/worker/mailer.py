"""Отправка обращения по e-mail на ТЕСТОВЫЙ адрес.

Это модельная интеграция: ТЗ запрещает выдавать имитацию за настоящую интеграцию, поэтому
письмо уходит не в УК, а на APPEAL_TEST_EMAIL, и в теме, тексте, карточке заявки и чате это сказано прямо.
Для пилота достаточно заменить адрес получателя на e-mail УК из настроек дома.
"""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import make_msgid

import structlog

from domovoy.core.config import get_settings
from domovoy.core.storage import read_object
from domovoy.modules.issues.models import Issue

log = structlog.get_logger(__name__)

MAX_PHOTOS = 5
TEST_BANNER = (
    "ТЕСТОВОЕ ПИСЬМО. Модельная интеграция сервиса «Домовой Кузя»: обращение отправлено на тестовый адрес "
    "вместо адреса управляющей организации{uk}. В пилоте получателем станет e-mail УК из настроек дома."
)


def enabled() -> bool:
    s = get_settings()
    return bool(s.appeal_test_email and s.smtp_host)


def _send_sync(msg: EmailMessage) -> None:
    s = get_settings()
    password = s.smtp_password.get_secret_value()
    if s.smtp_ssl:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ssl.create_default_context(), timeout=20) as smtp:
            if s.smtp_user:
                smtp.login(s.smtp_user, password)
            smtp.send_message(msg)
        return
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20) as smtp:
        if s.smtp_starttls:
            smtp.starttls(context=ssl.create_default_context())
        if s.smtp_user:
            smtp.login(s.smtp_user, password)
        smtp.send_message(msg)


async def send_appeal(issue: Issue, appeal_text: str) -> str | None:
    """Отправляет обращение на тестовый адрес. Возвращает адрес получателя или None, если отправка выключена."""
    if not enabled():
        return None
    s = get_settings()
    uk = issue.responsible_org
    uk_hint = f" ({uk.name}, {uk.email})" if uk and uk.email else (f" ({uk.name})" if uk else "")
    msg = EmailMessage()
    msg["Subject"] = f"[ТЕСТ] Коллективное обращение № {issue.id}: {issue.title}"
    msg["From"] = s.smtp_from
    msg["To"] = s.appeal_test_email
    msg["Message-ID"] = make_msgid(domain="domovoy.local")
    msg["X-Domovoy-Model-Integration"] = "true"
    msg.set_content(f"{TEST_BANNER.format(uk=uk_hint)}\n\n{'-' * 60}\n\n{appeal_text}\n")
    for i, key in enumerate((issue.photos or [])[:MAX_PHOTOS], start=1):
        try:
            data = await read_object(key)
        except Exception:
            log.warning("mailer.photo_missing", key=key, exc_info=True)
            continue
        msg.add_attachment(data, maintype="image", subtype="jpeg", filename=f"obrashchenie-{issue.id}-foto-{i}.jpg")
    await asyncio.to_thread(_send_sync, msg)
    log.info("mailer.appeal_sent", issue_id=issue.id, to=s.appeal_test_email)
    return s.appeal_test_email
