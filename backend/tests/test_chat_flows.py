"""Функционал Кузи в чате без мини-приложения: команды, кнопки, черновик заявки, намерения заглушки."""

import pytest

from domovoy.agent.stub import pick_intent
from domovoy.bot import chat_flows as flows
from domovoy.bot import photos, ui

TOOLS = {"create_issue", "list_issues", "vote_issue", "search_house", "nearest_shelters"}


class TestCommands:
    @pytest.mark.parametrize(
        ("text", "command"),
        [
            ("/новая", "report"),
            ("/проблемы", "issues"),
            ("/мои", "mine"),
            ("/события@kuzya_bot", "events"),
            ("/вещи", "market"),
            ("/укрытия", "shelters"),
            ("/профиль", "profile"),
            ("/дом", "houses"),
            ("Меню", "menu"),
        ],
    )
    def test_known(self, text: str, command: str) -> None:
        assert flows.command_of(text) == command

    def test_ordinary_text_is_not_a_command(self) -> None:
        assert flows.command_of("Кузя, какие проблемы в доме?") is None
        assert flows.command_of("") is None


class TestCallbacks:
    def test_new_actions_go_to_flows(self) -> None:
        for payload in ("menu:issues", "report:send", "issue:5", "status:5:resolved", "listing:3", "house:2"):
            assert flows.is_flow_callback(payload)

    def test_old_vote_and_join_stay_in_handlers(self) -> None:
        # сообщения заявок и событий в чате дома уже разосланы с такими кнопками
        assert not flows.is_flow_callback("vote:5")
        assert not flows.is_flow_callback("join:7")
        assert flows.is_flow_callback("vote:5:card")
        assert flows.is_flow_callback("join:7:list")

    def test_unknown_is_not_ours(self) -> None:
        assert not flows.is_flow_callback("something:1")


class TestFormat:
    @pytest.mark.parametrize(
        ("hours", "text"),
        [(1, "1 час"), (24, "1 сутки"), (72, "3 суток"), (168, "7 суток"), (720, "30 дней"), (3, "3 часа")],
    )
    def test_hours(self, hours: int, text: str) -> None:
        assert ui.fmt_hours(hours) == text

    def test_strip_kuzya(self) -> None:
        assert flows.strip_kuzya("Кузя, течёт крыша") == "течёт крыша"
        assert flows.strip_kuzya("течёт крыша") == "течёт крыша"
        assert flows.strip_kuzya("Кузя") == ""


class TestPhotos:
    def test_image_urls_from_max_attachments(self) -> None:
        body = {
            "text": "течёт",
            "attachments": [
                {"type": "image", "payload": {"url": "https://i.max.ru/1.jpg", "token": "t"}},
                {"type": "file", "payload": {"url": "https://x/doc.pdf"}},
                {"type": "image", "payload": {}},
            ],
        }
        assert photos.image_urls(body) == ["https://i.max.ru/1.jpg"]

    async def test_data_url_from_emulator(self) -> None:
        raw = await photos._download("data:image/png;base64,aGVsbG8=")
        assert raw == b"hello"


class TestMenu:
    def test_dm_menu_has_house_switch_and_app(self) -> None:
        payloads = [b.get("payload") for row in flows.main_menu(dm=True) for b in row]
        assert "menu:report" in payloads and "menu:houses" in payloads and "home" in payloads

    def test_group_menu_has_no_house_switch(self) -> None:
        payloads = [b.get("payload") for row in flows.main_menu(dm=False) for b in row]
        assert "menu:houses" not in payloads


class TestStubIntents:
    @pytest.mark.parametrize(
        "text", ["Кузя, пахнет газом в подъезде", "заведи заявку: течёт кран в подвале", "нет горячей воды с утра"]
    )
    def test_problem_reports_create_issue(self, text: str) -> None:
        intent = pick_intent(text, TOOLS)
        assert intent is not None and intent[0] == "create_issue"

    @pytest.mark.parametrize(("text", "issue_id"), [("поддерживаю заявку 5", 5), ("голос за №12", 12)])
    def test_vote_by_text(self, text: str, issue_id: int) -> None:
        assert pick_intent(text, TOOLS) == ("vote_issue", {"issue_id": issue_id})


class TestReviewFixes:
    def test_event_phrase_is_not_a_vote(self) -> None:
        intent = pick_intent("голосую за субботник в 11 у площадки", TOOLS)
        assert intent is None or intent[0] != "vote_issue"

    @pytest.mark.parametrize(
        "url",
        [
            "http://i.max.ru/1.jpg",
            "https://localhost/1.jpg",
            "https://127.0.0.1/1.jpg",
            "https://10.0.0.5/1.jpg",
            "https://minio.local/1.jpg",
            "not a url",
        ],
    )
    def test_photo_url_must_be_public_https(self, url: str) -> None:
        assert not photos._allowed_url(url)

    def test_public_https_photo_url_allowed(self) -> None:
        assert photos._allowed_url("https://i.oneme.ru/i?r=abc")

    def test_draft_after_card_lets_text_pass(self) -> None:
        key = (777, 888)
        flows._drafts[key] = flows.Draft(house_id=1, stage="confirm", text="течёт")
        try:
            assert not flows.draft_wants(*key, has_photos=False)
            assert flows.draft_wants(*key, has_photos=True)
        finally:
            flows._drafts.pop(key, None)
