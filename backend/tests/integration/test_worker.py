"""Воркер: обращение после порога голосов, тестовое письмо, напоминания о событиях и эскалация просрочек."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from types import SimpleNamespace

import pytest
from fakes import FakeBroker
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from domovoy.core.config import get_settings
from domovoy.core.db import get_sessionmaker
from domovoy.core.storage import save_bytes
from domovoy.modules.events.models import Event, EventParticipant
from domovoy.modules.issues import service as issues
from domovoy.modules.issues.models import Issue, IssueUpdate
from domovoy.modules.users.models import House, User
from domovoy.worker import mailer
from domovoy.worker import main as worker
from integration.helpers import Home, png_bytes

pytestmark = pytest.mark.integration


async def new_issue(
    home: Home, text: str = "Сломаны качели на детской площадке", photos: list[str] | None = None
) -> int:
    async with get_sessionmaker()() as s:
        user = await s.get(User, home.residents[0].id)
        house = await s.get(House, home.house.id)
        assert user and house
        issue = await issues.create_issue(s, user=user, house=house, description=text, photos=photos)
        return issue.id


async def mark_sent(issue_id: int, *, deadline: datetime | None = None) -> None:
    now = datetime.now(UTC)
    async with get_sessionmaker()() as s:
        await s.execute(
            update(Issue)
            .where(Issue.id == issue_id)
            .values(status="sent", sent_at=now - timedelta(hours=30), deadline_at=deadline or now + timedelta(hours=1))
        )
        await s.commit()


class TestDispatch:
    async def test_appeal_is_saved_and_announced(self, home: Home, broker: FakeBroker, session: AsyncSession) -> None:
        issue_id = await new_issue(home)
        await mark_sent(issue_id)
        broker.published.clear()

        await worker.dispatch_issue(issue_id)

        issue = await session.get(Issue, issue_id)
        assert issue is not None and issue.appeal_text
        assert issue.appeal_text.startswith(f"Кому: {home.uk.name}")
        assert f"ОБРАЩЕНИЕ № {issue_id}" in issue.appeal_text
        assert home.house.address in issue.appeal_text
        assert issue.appeal_channel == "model"
        last = await session.scalar(
            select(IssueUpdate.note).where(IssueUpdate.issue_id == issue_id).order_by(IssueUpdate.id.desc()).limit(1)
        )
        assert last is not None and "Письмо не отправлялось" in last
        # жителям честно говорим, что это тестовый режим
        (chat,) = broker.sent(chat_id=home.chat_id)
        assert "тестовом режиме" in chat["text"]
        assert chat["buttons"][0][0]["payload"] == f"issue:{issue_id}"
        (author,) = broker.sent(user_id=home.residents[0].max_user_id)
        assert author["text"].startswith("📨 Соседи поддержали вашу заявку")
        assert broker.events("issue.updated", home.house.id)

    async def test_second_dispatch_does_nothing(self, home: Home, broker: FakeBroker) -> None:
        issue_id = await new_issue(home)
        await mark_sent(issue_id)
        await worker.dispatch_issue(issue_id)
        broker.published.clear()
        await worker.dispatch_issue(issue_id)
        await worker.dispatch_issue(10**8)
        assert broker.published == []

    async def test_test_email_with_photos(
        self, home: Home, monkeypatch: pytest.MonkeyPatch, session: AsyncSession
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "smtp_host", "smtp.test")
        monkeypatch.setattr(settings, "appeal_test_email", "appeals@example.org")
        sent: list[EmailMessage] = []
        monkeypatch.setattr(mailer, "_send_sync", sent.append)
        keys = [await save_bytes("issues", png_bytes()), "issues/missing.jpg"]
        issue_id = await new_issue(home, photos=keys)
        await mark_sent(issue_id)

        await worker.dispatch_issue(issue_id)

        (msg,) = sent
        assert msg["To"] == "appeals@example.org"
        assert msg["Subject"].startswith(f"[ТЕСТ] Коллективное обращение № {issue_id}")
        assert msg["X-Domovoy-Model-Integration"] == "true"
        body = msg.get_body(("plain",))
        assert body is not None and "ТЕСТОВОЕ ПИСЬМО" in body.get_content()
        # одно фото на месте, второго нет в хранилище: письмо уходит с тем, что нашлось
        assert [a.get_filename() for a in msg.iter_attachments()] == [f"obrashchenie-{issue_id}-foto-1.jpg"]
        issue = await session.get(Issue, issue_id)
        assert issue is not None and issue.appeal_channel == "test_email:appeals@example.org"

    async def test_failed_email_keeps_appeal_in_card(
        self, home: Home, monkeypatch: pytest.MonkeyPatch, session: AsyncSession, broker: FakeBroker
    ) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "smtp_host", "smtp.test")
        monkeypatch.setattr(settings, "appeal_test_email", "appeals@example.org")

        def broken(_: EmailMessage) -> None:
            raise OSError("smtp down")

        monkeypatch.setattr(mailer, "_send_sync", broken)
        issue_id = await new_issue(home)
        await mark_sent(issue_id)
        await worker.dispatch_issue(issue_id)

        issue = await session.get(Issue, issue_id)
        assert issue is not None and issue.appeal_text and issue.appeal_channel == "model"
        note = await session.scalar(
            select(IssueUpdate.note).where(IssueUpdate.issue_id == issue_id).order_by(IssueUpdate.id.desc()).limit(1)
        )
        assert note is not None and "Тестовое письмо не ушло" in note

    @pytest.mark.parametrize(
        ("ssl", "starttls", "login"), [(True, False, True), (False, True, True), (False, False, False)]
    )
    def test_smtp_modes(self, monkeypatch: pytest.MonkeyPatch, ssl: bool, starttls: bool, login: bool) -> None:
        calls: list[str] = []

        class FakeSmtp:
            def __init__(self, host: str, port: int, **kwargs: object) -> None:
                calls.append(f"connect:{host}:{port}")

            def __enter__(self) -> "FakeSmtp":
                return self

            def __exit__(self, *exc: object) -> None:
                calls.append("quit")

            def starttls(self, **kwargs: object) -> None:
                calls.append("starttls")

            def login(self, user: str, password: str) -> None:
                calls.append(f"login:{user}:{password}")

            def send_message(self, msg: EmailMessage) -> None:
                calls.append("send")

        settings = get_settings()
        monkeypatch.setattr(settings, "smtp_host", "smtp.test")
        monkeypatch.setattr(settings, "smtp_ssl", ssl)
        monkeypatch.setattr(settings, "smtp_starttls", starttls)
        monkeypatch.setattr(settings, "smtp_user", "kuzya" if login else "")
        monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSmtp)
        monkeypatch.setattr(mailer.smtplib, "SMTP_SSL", FakeSmtp)

        mailer._send_sync(EmailMessage())

        assert calls[0].startswith("connect:smtp.test")
        assert ("starttls" in calls) is starttls
        assert any(c.startswith("login:kuzya") for c in calls) is login
        assert calls[-2:] == ["send", "quit"]


class TestEscalation:
    async def test_overdue_issue_gets_complaint_once(
        self, home: Home, broker: FakeBroker, session: AsyncSession
    ) -> None:
        issue_id = await new_issue(home)
        await mark_sent(issue_id, deadline=datetime.now(UTC) - timedelta(hours=2))
        broker.published.clear()

        await worker.escalate_overdue()

        issue = await session.get(Issue, issue_id)
        assert issue is not None and issue.escalated_at is not None
        note = await session.scalar(
            select(IssueUpdate.note).where(IssueUpdate.issue_id == issue_id).order_by(IssueUpdate.id.desc()).limit(1)
        )
        assert note is not None and note.startswith("Срок истёк")
        assert "Кому: Агентство государственного строительного и жилищного надзора" in note
        (msg,) = broker.sent(chat_id=home.chat_id)
        assert msg["buttons"][0][0]["payload"] == f"complaint:{issue_id}"

        broker.published.clear()
        await worker.escalate_overdue()
        assert broker.sent(chat_id=home.chat_id) == []

    async def test_issue_in_time_is_not_escalated(self, home: Home, session: AsyncSession) -> None:
        issue_id = await new_issue(home)
        await mark_sent(issue_id, deadline=datetime.now(UTC) + timedelta(hours=5))
        await worker.escalate_overdue()
        issue = await session.get(Issue, issue_id)
        assert issue is not None and issue.escalated_at is None


class TestReminders:
    async def test_participants_and_chat_are_reminded_once(
        self, home: Home, broker: FakeBroker, session: AsyncSession
    ) -> None:
        soon = Event(
            house_id=home.house.id,
            author_id=home.admin.id,
            title="Субботник у третьего подъезда",
            kind="subbotnik",
            starts_at=datetime.now(UTC) + timedelta(minutes=45),
            place="У третьего подъезда",
            participants_count=2,
        )
        later = Event(
            house_id=home.house.id,
            author_id=home.admin.id,
            title="Собрание через неделю",
            kind="meeting",
            starts_at=datetime.now(UTC) + timedelta(days=7),
            place="Холл",
        )
        session.add_all([soon, later])
        await session.flush()
        session.add_all(EventParticipant(event_id=soon.id, user_id=u.id) for u in home.users[:2])
        await session.commit()

        await worker.remind_events()

        dms = [m for m in broker.payloads("bot.send") if m["user_id"] in {u.max_user_id for u in home.users}]
        assert len(dms) == 2
        assert all("Субботник у третьего подъезда" in m["text"] for m in dms)
        (chat,) = broker.sent(chat_id=home.chat_id)
        assert "Идут: Админ, Олег" in chat["text"]
        assert chat["buttons"][0][0]["payload"] == f"event_{soon.id}"
        await session.refresh(soon)
        await session.refresh(later)
        assert soon.reminded and not later.reminded

        broker.published.clear()
        await worker.remind_events()
        assert broker.sent(chat_id=home.chat_id) == []


class TestProcess:
    async def test_main_subscribes_and_dispatches(
        self, home: Home, broker: FakeBroker, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ticks: list[float] = []

        async def stop_after_tick(seconds: float) -> None:
            ticks.append(seconds)
            raise asyncio.CancelledError

        # подменяем asyncio только внутри модуля воркера: первая же пауза планировщика завершает процесс
        monkeypatch.setattr(worker, "asyncio", SimpleNamespace(sleep=stop_after_tick, gather=asyncio.gather))
        with pytest.raises(asyncio.CancelledError):
            await worker.main()
        assert ticks == [worker.TICK_SECONDS]
        assert broker.started == 0

        issue_id = await new_issue(home)
        await mark_sent(issue_id)
        broker.published.clear()
        await broker.handlers["issue.dispatch"]({"issue_id": issue_id})
        assert broker.sent(chat_id=home.chat_id)

    async def test_failing_job_does_not_stop_scheduler(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[str] = []

        async def broken() -> None:
            calls.append("broken")
            raise RuntimeError("boom")

        async def fine() -> None:
            calls.append("fine")

        async def stop(_: float) -> None:
            raise asyncio.CancelledError

        monkeypatch.setattr(worker, "remind_events", broken)
        monkeypatch.setattr(worker, "escalate_overdue", fine)
        monkeypatch.setattr(worker, "asyncio", SimpleNamespace(sleep=stop))
        with pytest.raises(asyncio.CancelledError):
            await worker.scheduler()
        assert calls == ["broken", "fine"]
