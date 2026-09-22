"""Тесты критичной логики без внешних сервисов: безопасность, модерация, разбор дат, классификация."""

import json
from datetime import datetime
from urllib.parse import quote

import pytest

from domovoy.agent.mcp_tools import UnsafeMcpUrlError, ensure_public_url
from domovoy.agent.stub import pick_intent
from domovoy.agent.timeparse import TZ, parse_when
from domovoy.agent.tools import infer_kind
from domovoy.core.embeddings import embed
from domovoy.core.max_auth import InitDataError, sign, validate_init_data
from domovoy.modules.issues.classifier import classify_rules
from domovoy.modules.moderation.guardrails import check_rules
from domovoy.modules.users.pulse import PulseStats, compute_score, mood_for

TOKEN = "test-bot-token"
NOW = 1_790_000_000


def make_init_data(token: str = TOKEN, auth_date: int = NOW, **extra: str) -> str:
    pairs = {
        "auth_date": str(auth_date),
        "query_id": "q1",
        "user": json.dumps({"id": 1001, "first_name": "Анна"}, ensure_ascii=False),
        "chat": json.dumps({"id": -100, "type": "CHAT"}),
        **extra,
    }
    pairs["hash"] = sign(pairs, token)
    return "&".join(f"{k}={quote(v)}" for k, v in pairs.items())


class TestInitData:
    def test_valid_signature_is_accepted(self) -> None:
        data = validate_init_data(make_init_data(start_param="issue_5"), TOKEN, 3600, now=NOW + 10)
        assert data.user["id"] == 1001
        assert data.chat == {"id": -100, "type": "CHAT"}
        assert data.start_param == "issue_5"

    def test_foreign_token_is_rejected(self) -> None:
        with pytest.raises(InitDataError, match="Подпись"):
            validate_init_data(make_init_data(token="other"), TOKEN, 3600, now=NOW)

    def test_tampered_user_is_rejected(self) -> None:
        raw = make_init_data().replace("1001", "1002")
        with pytest.raises(InitDataError):
            validate_init_data(raw, TOKEN, 3600, now=NOW)

    def test_expired_is_rejected(self) -> None:
        with pytest.raises(InitDataError, match="устарела"):
            validate_init_data(make_init_data(), TOKEN, 3600, now=NOW + 7200)

    def test_duplicate_key_is_rejected(self) -> None:
        with pytest.raises(InitDataError, match="повторяется"):
            validate_init_data(make_init_data() + "&auth_date=1", TOKEN, 3600, now=NOW)


class TestGuardrails:
    @pytest.mark.parametrize(
        "text",
        ["Ты дурак, блин", "да пошёл ты нах*й", "х у й тебе", "Заработок от 100000 в день, пиши в личку t.me/xxx"],
    )
    def test_blocks_abuse_and_spam(self, text: str) -> None:
        assert check_rules(text).blocked

    @pytest.mark.parametrize(
        "text",
        [
            "Ребята, кто оставил коляску у лифта?",
            "Небо сегодня красивое, пойдём на субботник",
            "Употребляю только фильтрованную воду",
            "УК опять не вывезла мусор, это безобразие",
            "Отдам дрель, пишите https://example.org",
        ],
    )
    def test_allows_normal_messages(self, text: str) -> None:
        assert not check_rules(text).blocked


class TestTimeParse:
    now = datetime(2026, 9, 22, 12, 0, tzinfo=TZ)  # вторник

    def test_weekday_and_hour(self) -> None:
        assert parse_when("в субботу в 11", self.now) == datetime(2026, 9, 26, 11, 0, tzinfo=TZ)

    def test_tomorrow_with_minutes(self) -> None:
        assert parse_when("завтра в 18:30", self.now) == datetime(2026, 9, 23, 18, 30, tzinfo=TZ)

    def test_explicit_date(self) -> None:
        assert parse_when("25.10 в 10", self.now) == datetime(2026, 10, 25, 10, 0, tzinfo=TZ)

    def test_evening_shift(self) -> None:
        assert parse_when("в пятницу в 7 вечера", self.now) == datetime(2026, 9, 25, 19, 0, tzinfo=TZ)

    def test_subbotnik_word_is_not_saturday(self) -> None:
        assert parse_when("создай субботник в воскресенье в 12", self.now) == datetime(2026, 9, 27, 12, 0, tzinfo=TZ)

    def test_no_date(self) -> None:
        assert parse_when("когда-нибудь", self.now) is None


class TestClassifierAndSearch:
    @pytest.mark.parametrize(
        ("text", "category"),
        [
            ("Течёт крыша над 9 этажом", "roof"),
            ("В подъезде пахнет газом", "gas"),
            ("Лифт застрял между этажами", "elevator"),
            ("Контейнеры переполнены, мусор не вывозят", "garbage"),
            ("Огромная яма на дороге у въезда", "road"),
            ("Течёт крыша над 9 этажом, после дождя лужа в подъезде", "roof"),
            ("Не горит свет на лестнице 1 подъезда", "electricity"),
        ],
    )
    def test_rules(self, text: str, category: str) -> None:
        assert classify_rules(text).category == category

    def test_similar_texts_are_closer(self) -> None:
        def cos(a: list[float], b: list[float]) -> float:
            return sum(x * y for x, y in zip(a, b, strict=True))

        base = embed("Протекает крыша, капает с потолка")
        assert cos(base, embed("течь кровли над девятым этажом")) > cos(base, embed("сломались качели во дворе"))


class TestAgentStub:
    tools = frozenset(
        {"create_event", "list_issues", "nearest_shelters", "create_issue", "search_house", "list_events"}
    )

    def test_create_event_intent(self) -> None:
        tool, args = pick_intent("Кузя, создай субботник в субботу в 11 у площадки", self.tools) or ("", {})
        assert tool == "create_event"
        assert args["title"] == "Субботник во дворе"

    def test_shelter_intent(self) -> None:
        assert (pick_intent("Где ближайшее укрытие?", self.tools) or ("",))[0] == "nearest_shelters"

    def test_event_kind_from_title(self) -> None:
        assert infer_kind("Субботник во дворе") == "subbotnik"
        assert infer_kind("Собрание жителей") == "meeting"

    def test_greeting_needs_no_tool(self) -> None:
        assert pick_intent("Привет, Кузя!", self.tools) is None


@pytest.mark.parametrize("url", ["http://127.0.0.1:8765/mcp", "http://169.254.169.254/latest", "ftp://example.org"])
async def test_mcp_registry_blocks_internal_urls(url: str) -> None:
    with pytest.raises(UnsafeMcpUrlError):
        await ensure_public_url(url)


def test_pulse_mood() -> None:
    calm = PulseStats(
        open_issues=1, overdue_issues=0, resolved_30d=3, upcoming_events=1, active_listings=4, active_alert=False
    )
    bad = PulseStats(
        open_issues=6, overdue_issues=2, resolved_30d=0, upcoming_events=0, active_listings=0, active_alert=False
    )
    assert mood_for(compute_score(calm), False) == "happy"
    assert mood_for(compute_score(bad), False) == "sad"
    assert mood_for(90, True) == "alarm"
