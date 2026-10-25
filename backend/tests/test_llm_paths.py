"""Ветки с настоящей LLM без сети: модель-заглушка отвечает заданным результатом или падает.

Проверяем главное правило: LLM только помогает (категория, модерация, деловой стиль), а при любой ошибке
сервис работает по правилам. Газ всегда определяется правилами.
"""

from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langchain_ollama import ChatOllama

from domovoy.agent import llm, stub
from domovoy.agent.stub import StubChatModel
from domovoy.agent.timeparse import TZ, parse_when
from domovoy.core.config import get_settings
from domovoy.modules.issues import classifier
from domovoy.modules.moderation import guardrails
from domovoy.modules.users.pulse import PulseStats, phrase_for
from domovoy.worker import appeal


class FakeLlm:
    """Минимум интерфейса ChatModel, который использует код: ainvoke и with_structured_output."""

    def __init__(self, answer: Any = None, error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.prompts: list[str] = []

    def with_structured_output(self, schema: type) -> "FakeLlm":
        return self

    async def ainvoke(self, prompt: str) -> Any:
        self.prompts.append(prompt)
        if self.error:
            raise self.error
        return self.answer


@pytest.fixture
def real_llm(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(model: FakeLlm, *modules: Any) -> FakeLlm:
        for module in modules:
            monkeypatch.setattr(module, "is_real_llm", lambda: True)
            monkeypatch.setattr(module, "get_llm", lambda: model)
        return model

    return install


class TestClassifier:
    async def test_llm_picks_category_and_title(self, real_llm: Any) -> None:
        model = real_llm(
            FakeLlm(classifier.LlmClassification(category="roof", title="Протечка", confidence=0.9)), classifier
        )
        result = await classifier.classify("Капает с потолка на девятом")
        assert (result.category, result.title, result.source) == ("roof", "Протечка", "llm")
        assert "roof - " in model.prompts[0]

    async def test_gas_is_always_by_rules(self, real_llm: Any) -> None:
        model = real_llm(FakeLlm(error=AssertionError("модель не должна вызываться")), classifier)
        result = await classifier.classify("В подъезде пахнет газом")
        assert (result.category, result.source) == ("gas", "rules") and model.prompts == []

    async def test_llm_failure_falls_back_to_rules(self, real_llm: Any) -> None:
        real_llm(FakeLlm(error=TimeoutError("ollama")), classifier)
        result = await classifier.classify("Лифт застрял между этажами")
        assert (result.category, result.source) == ("elevator", "rules")

    def test_long_title_is_cut(self) -> None:
        title = classifier.make_title("очень " * 30)
        assert title.endswith("...") and len(title) <= 70 and title[0] == "О"
        assert classifier.make_title("   ") == "Проблема в доме"


class TestModeration:
    async def test_llm_blocks_hidden_rudeness(self, real_llm: Any) -> None:
        real_llm(FakeLlm(guardrails.LlmVerdict(toxic=True, reason="травля соседа")), guardrails)
        verdict = await guardrails.moderate("Некоторым жильцам третьего этажа лучше бы переехать отсюда")
        assert verdict.blocked and verdict.reasons == ["травля соседа"]

    async def test_llm_ok_and_failure_keep_rules_result(self, real_llm: Any) -> None:
        text = "УК опять не вывезла мусор, это безобразие какое-то"
        real_llm(FakeLlm(guardrails.LlmVerdict(toxic=False, reason="")), guardrails)
        assert not (await guardrails.moderate(text)).blocked
        real_llm(FakeLlm(error=RuntimeError("down")), guardrails)
        assert not (await guardrails.moderate(text)).blocked

    async def test_short_text_skips_llm(self, real_llm: Any) -> None:
        model = real_llm(FakeLlm(error=AssertionError("не нужно")), guardrails)
        assert not (await guardrails.moderate("Всем привет")).blocked
        assert model.prompts == []

    def test_caps_is_a_warning(self) -> None:
        verdict = guardrails.check_rules("ПОЧЕМУ ОПЯТЬ НЕТ ГОРЯЧЕЙ ВОДЫ В ДОМЕ")
        assert verdict.verdict == "warn" and not verdict.blocked


class TestAppealStyle:
    issue = cast(Any, SimpleNamespace(title="Течёт крыша", description="Капает на 9 этаже"))

    async def test_llm_rewrites_description(self, real_llm: Any) -> None:
        real_llm(FakeLlm(SimpleNamespace(content="  Протечка кровли над 9 этажом.  ")), appeal)
        assert await appeal.business_description(self.issue) == "Протечка кровли над 9 этажом."

    @pytest.mark.parametrize("model", [FakeLlm(SimpleNamespace(content="   ")), FakeLlm(error=RuntimeError("x"))])
    async def test_empty_or_failed_rewrite_keeps_resident_text(self, real_llm: Any, model: FakeLlm) -> None:
        real_llm(model, appeal)
        assert await appeal.business_description(self.issue) == "Течёт крыша. Капает на 9 этаже"


class TestLlmFactory:
    @pytest.fixture(autouse=True)
    def fresh_cache(self) -> Any:
        llm.get_llm.cache_clear()
        yield
        llm.get_llm.cache_clear()

    def test_stub_by_default(self) -> None:
        assert isinstance(llm.get_llm(), StubChatModel) and not llm.is_real_llm()

    def test_cloud_needs_key_local_does_not(self, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "llm_provider", "ollama_cloud")
        assert isinstance(llm.get_llm(), StubChatModel)  # без ключа облако не подключаем
        llm.get_llm.cache_clear()
        monkeypatch.setattr(settings, "ollama_api_key", type(settings.ollama_api_key)("key"))
        monkeypatch.setattr(settings, "ollama_cloud_url", "https://cloud.ollama.test")
        monkeypatch.setattr(settings, "ollama_local_url", "http://ollama.local.test:11434")
        cloud = llm.get_llm()
        assert isinstance(cloud, ChatOllama) and cloud.base_url == "https://cloud.ollama.test" and llm.is_real_llm()
        llm.get_llm.cache_clear()
        monkeypatch.setattr(settings, "llm_provider", "ollama_local")
        local = llm.get_llm()
        assert isinstance(local, ChatOllama) and local.base_url == "http://ollama.local.test:11434"


class TestStubTalk:
    def test_mcp_json_is_retold_as_lines(self) -> None:
        text = stub._humanize(
            '{"items": [{"work": "Ремонт крыши", "planned_years": "2027"}, "строка"], "source": "демо"}'
        )
        assert text == "• Ремонт крыши, годы 2027\n• строка\n(демо)"
        assert stub._humanize("[1, 2]") == "• 1\n• 2"
        assert stub._humanize('"просто строка"') == '"просто строка"'
        assert stub._humanize("не json") == "не json"

    def test_speaker_from_system_prompt(self) -> None:
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [SystemMessage(content="Собеседник: Ильдар Галиев. Дом: 7"), HumanMessage(content="без подписи")]
        assert stub._speaker(messages) == "Ильдар"
        assert stub._speaker([HumanMessage(content="тоже без подписи")]) == "сосед"
        assert stub._last_human([SystemMessage(content="x")]) == ""

    async def test_unknown_request_gets_hint(self) -> None:
        from langchain_core.messages import HumanMessage

        model = StubChatModel()
        reply = await model.ainvoke([HumanMessage(content="[Анна Иванова]: ммм")])
        assert str(reply.content).startswith("Анна, я пока не понял")


class TestPulsePhrases:
    def stats(self, **values: int | bool) -> PulseStats:
        base: dict[str, Any] = {
            "open_issues": 0,
            "overdue_issues": 0,
            "resolved_30d": 0,
            "upcoming_events": 0,
            "active_listings": 0,
            "active_alert": False,
        }
        return PulseStats(**{**base, **values})

    @pytest.mark.parametrize(
        ("mood", "values", "start"),
        [
            ("alarm", {}, "Тревога!"),
            ("ok", {"overdue_issues": 2}, "Просрочено заявок: 2"),
            ("happy", {"upcoming_events": 1}, "Дом в порядке, а скоро событие"),
            ("happy", {}, "В доме тепло и спокойно"),
            ("ok", {"open_issues": 3}, "Открытых заявок: 3"),
            ("worried", {}, "Накопилось много заявок"),
            ("sad", {}, "Мне грустно"),
        ],
    )
    def test_phrase(self, mood: Any, values: dict[str, int], start: str) -> None:
        assert phrase_for(mood, self.stats(**values)).startswith(start)


class TestDates:
    now = datetime(2026, 9, 22, 12, 0, tzinfo=TZ)  # вторник

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("2026-10-01T15:00:00+03:00", datetime(2026, 10, 1, 15, 0, tzinfo=TZ)),
            ("послезавтра в 3 дня", datetime(2026, 9, 24, 15, 0, tzinfo=TZ)),
            ("сегодня вечером в 8 вечера", datetime(2026, 9, 22, 20, 0, tzinfo=TZ)),
            ("01.09 в 10", datetime(2027, 9, 1, 10, 0, tzinfo=TZ)),
            ("05.10.27 в 9:15", datetime(2027, 10, 5, 9, 15, tzinfo=TZ)),
            ("завтра", datetime(2026, 9, 23, 11, 0, tzinfo=TZ)),
        ],
    )
    def test_parse(self, text: str, expected: datetime) -> None:
        assert parse_when(text, self.now) == expected

    def test_impossible_date(self) -> None:
        assert parse_when("31.02 в 10", self.now) is None
