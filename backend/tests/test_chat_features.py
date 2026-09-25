"""Упоминание бота в чате, объявления через stub-агента, подписанные ссылки на документы."""

import pytest

from domovoy.agent.stub import pick_intent
from domovoy.bot import handlers
from domovoy.bot.gateway import media_of
from domovoy.bot.handlers import addressed_to_bot, strip_mentions
from domovoy.modules.documents.router import _sign

TOOLS = {"create_announcement", "create_event", "list_events", "list_listings", "create_issue", "search_house"}


@pytest.fixture(autouse=True)
def bot_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handlers.BOT, "user_id", 732818139220)
    monkeypatch.setattr(handlers.BOT, "username", "id732818139220_bot")


class TestMention:
    def test_username_in_text(self) -> None:
        assert addressed_to_bot("@id732818139220_bot сделай объявление", {}, None)

    def test_markup_mention_with_display_name(self) -> None:
        body = {"markup": [{"type": "user_mention", "from": 0, "length": 13, "user_id": 732818139220}]}
        assert addressed_to_bot("@Домовой Бот сделай объявление", body, None)

    def test_mention_of_other_user_is_ignored(self) -> None:
        body = {"markup": [{"type": "user_mention", "from": 0, "length": 5, "user_id": 42}]}
        assert not addressed_to_bot("@Олег привет", body, None)

    def test_reply_to_bot(self) -> None:
        link = {"type": "reply", "sender": {"user_id": 732818139220, "is_bot": True}, "message": {}}
        assert addressed_to_bot("а когда?", {}, link)

    def test_plain_chat_message_is_not_for_bot(self) -> None:
        assert not addressed_to_bot("соседи, кто брал мой самокат?", {}, None)

    def test_by_name(self) -> None:
        assert addressed_to_bot("Кузя, какие проблемы?", {}, None)

    def test_strip_markup_and_username(self) -> None:
        body = {"markup": [{"type": "user_mention", "from": 0, "length": 13, "user_id": 732818139220}]}
        assert strip_mentions("@Домовой Бот сделай объявление", body) == "сделай объявление"
        assert strip_mentions("@id732818139220_bot сделай объявление о субботнике", {}) == (
            "сделай объявление о субботнике"
        )


class TestAnnouncementIntent:
    def test_announcement_about_subbotnik_without_date(self) -> None:
        tool, args = pick_intent("сделай объявление о субботнике", TOOLS) or ("", {})
        assert tool == "create_announcement"
        assert args["title"] == "Субботник во дворе"
        assert args["when"] == ""

    def test_announcement_with_date_creates_event_too(self) -> None:
        tool, args = pick_intent("Кузя, сделай объявление о субботнике в субботу в 11 у площадки", TOOLS) or ("", {})
        assert tool == "create_announcement"
        assert args["when"]
        assert args["place"] == "у площадки"

    def test_free_text_announcement(self) -> None:
        tool, args = pick_intent("Кузя, напиши всем объявление что завтра отключат горячую воду", TOOLS) or ("", {})
        assert tool == "create_announcement"
        assert args["title"].startswith("Завтра отключат горячую воду")

    def test_market_question_still_goes_to_market(self) -> None:
        assert pick_intent("что на барахолке, есть объявления?", TOOLS) == ("list_listings", {})

    def test_make_event_with_sdelay(self) -> None:
        tool, _ = pick_intent("Кузя, сделай субботник в воскресенье в 12", TOOLS) or ("", {})
        assert tool == "create_event"


class TestMedia:
    def test_keeps_images_drops_keyboard(self) -> None:
        body = {
            "attachments": [
                {"type": "image", "payload": {"token": "t1", "url": "https://x/1.jpg", "photo_id": 1}},
                {"type": "inline_keyboard", "payload": {"buttons": []}},
            ]
        }
        assert media_of(body) == [{"type": "image", "payload": {"token": "t1"}}]


def test_document_link_signature_depends_on_id_and_expiry() -> None:
    assert _sign(1, 100) == _sign(1, 100)
    assert _sign(1, 100) != _sign(2, 100)
    assert _sign(1, 100) != _sign(1, 101)
