"""Stub-LLM: детерминированная модель без сети.

Нужна, чтобы весь контур (LangGraph ReAct-агент, инструменты, MCP, бот) работал
в мок-режиме и на проверке без ключей. Модель распознаёт намерение по ключевым словам,
вызывает подходящий инструмент и пересказывает его ответ вежливо и от лица Кузи.
"""

import json
import re
from collections.abc import Sequence
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool

NAME_RE = re.compile(r"Собеседник:\s*([^\n(]+)")
SPEAKER_RE = re.compile(r"^\[([^\]]+)\]:\s*")

# (ключевые корни, имя инструмента); порядок важен: сначала более конкретные намерения.
CREATE_EVENT_WORDS = ("созда", "организ", "устро", "запланир", "собер", "проведем", "давайте")
EVENT_WORDS = ("субботник", "мероприят", "событи", "праздник", "встреч", "собрани", "пикник", "турнир")
INTENTS: tuple[tuple[tuple[str, ...], str], ...] = (
    # инструменты MCP-сервера «Жилищный навигатор» (подключается к агенту по MCP)
    (("тариф", "сколько стоит вода", "стоимость отоплен"), "gis_zhkh__utility_tariffs"),
    (("капремонт", "капитальн"), "gis_zhkh__capital_repair_plan"),
    (("паспорт дома", "год постройки", "сколько этажей"), "gis_zhkh__house_passport"),
    (("укрыт", "убежищ", "бомбоуб", "беспилот", "тревог", "дрон", "бпла"), "nearest_shelters"),
    (
        ("не работает", "сломал", "течет", "протека", "сообщи о проблем", "новая заявк", "прорвал", "засор"),
        "create_issue",
    ),
    (("проблем", "заявк", "обращени", "жалоб"), "list_issues"),
    (EVENT_WORDS, "list_events"),
    (("барахол", "отдам", "отдаю", "продаю", "продам", "объявлен", "куплю", "даром"), "list_listings"),
    (("ачивк", "очк", "уровень", "рейтинг", "мой профиль", "награ"), "my_profile"),
    (("как дела", "как дом", "статус дома", "настроени", "как ты", "пульс"), "house_status"),
)
ACTION_TOOLS = frozenset({"create_event", "create_issue", "vote_issue"})
GREETINGS = ("привет", "здравств", "добрый", "доброе", "hello", "/start", "хай", "салют")
THANKS = ("спасибо", "благодар", "спс")


FIELD_TITLES = {
    "region": "Регион",
    "address": "Адрес",
    "title": "Дом",
    "uk": "Управляющая организация",
    "management": "Способ управления",
    "energy_class": "Класс энергоэффективности",
    "work": "",
    "planned_years": "годы",
    "status": "статус",
    "source": "Источник",
    "year_built": "Год постройки",
    "floors": "Этажей",
    "entrances": "Подъездов",
    "apartments": "Квартир",
    "wall_material": "Стены",
}


def _humanize(text: str) -> str:
    """Структурированный ответ MCP (JSON) пересказываем строками, как это сделала бы LLM."""
    try:
        data = json.loads(text)
    except ValueError:
        return text
    lines: list[str] = []

    def row(item: dict[str, Any]) -> str:
        if "price_rub" in item:
            return f"{item.get('service')}: {item['price_rub']} ₽ за {item.get('unit', 'ед.')}"
        return ", ".join(f"{FIELD_TITLES.get(k, k)} {v}".strip() for k, v in item.items())

    if isinstance(data, list):
        data = {"items": data}
    if not isinstance(data, dict):
        return text
    for key, value in data.items():
        if isinstance(value, list):
            lines.extend(f"• {row(v)}" if isinstance(v, dict) else f"• {v}" for v in value)
        elif key != "source" and value is not None:
            lines.append(f"{FIELD_TITLES.get(key, key)}: {value}")
    if data.get("source"):
        lines.append(f"({data['source']})")
    return "\n".join(lines)


def _last_human(messages: Sequence[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return SPEAKER_RE.sub("", str(msg.content)).strip()
    return ""


def _speaker(messages: Sequence[BaseMessage]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage) and (m := SPEAKER_RE.match(str(msg.content))):
            return m.group(1).split()[0]
    for msg in messages:
        if isinstance(msg, SystemMessage) and (m := NAME_RE.search(str(msg.content))):
            return m.group(1).strip().split()[0]
    return "сосед"


def pick_intent(text: str, tool_names: set[str] | frozenset[str]) -> tuple[str, dict[str, Any]] | None:
    low = text.lower().replace("ё", "е")
    wants_event = any(w in low for w in CREATE_EVENT_WORDS) and any(w in low for w in EVENT_WORDS)
    if wants_event and "create_event" in tool_names:
        return "create_event", {"title": _event_title(low), "when": text, "place": _place(text)}
    for words, tool in INTENTS:
        if tool in tool_names and any(w in low for w in words):
            if tool == "create_issue":
                return tool, {"description": text}
            if tool == "list_issues":
                return tool, {"status": "open"}
            return tool, {}
    if "search_house" in tool_names and len(low) > 12 and not any(g in low for g in GREETINGS):
        return "search_house", {"query": text}
    return None


def _event_title(low: str) -> str:
    for word, title in (
        ("субботник", "Субботник во дворе"),
        ("собрани", "Собрание жителей"),
        ("праздник", "Праздник двора"),
        ("пикник", "Пикник во дворе"),
        ("турнир", "Турнир во дворе"),
    ):
        if word in low:
            return title
    return "Встреча соседей"


def _place(text: str) -> str:
    m = re.search(r"\b(?:у|возле|около|на|во)\s+([а-яёА-ЯЁ0-9\s\-]{3,40}?)(?:[,.!]|$)", text)
    return m.group(0).strip(" ,.!") if m else "Во дворе"


class StubChatModel(BaseChatModel):
    tools: list[dict[str, Any]] = []  # noqa: RUF012  поле pydantic, копируется при bind_tools

    @property
    def _llm_type(self) -> str:
        return "domovoy-stub"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        return self.model_copy(update={"tools": [convert_to_openai_tool(t) for t in tools]})

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(generations=[ChatGeneration(message=self._respond(messages))])

    def _respond(self, messages: list[BaseMessage]) -> AIMessage:
        name = _speaker(messages)
        if messages and isinstance(messages[-1], ToolMessage):
            results = []
            for msg in reversed(messages):
                if not isinstance(msg, ToolMessage):
                    break
                results.append(_humanize(str(msg.content)))
            body = "\n\n".join(reversed(results))
            if messages[-1].name in ACTION_TOOLS:
                return AIMessage(content=f"{name}, {body[:1].lower()}{body[1:]}")
            return AIMessage(content=f"{name}, вот что я узнал:\n\n{body}")

        text = _last_human(messages)
        low = text.lower()
        tool_names = {t["function"]["name"] for t in self.tools}
        intent = pick_intent(text, tool_names)
        if intent:
            tool, args = intent
            return AIMessage(content="", tool_calls=[{"name": tool, "args": args, "id": f"call_{tool}"}])
        if any(t in low for t in THANKS):
            return AIMessage(content=f"Всегда рад помочь, {name}! Берегу дом вместе с вами.")
        if any(g in low for g in GREETINGS):
            return AIMessage(
                content=(
                    f"Привет, {name}! Я Домовой Кузя, хранитель вашего дома. "
                    "Могу завести заявку о поломке, собрать соседей на субботник, "
                    "подсказать ближайшее укрытие или найти вещь на барахолке. Чем помочь?"
                )
            )
        return AIMessage(
            content=(
                f"{name}, я пока не понял, чем помочь. Попробуй так: «Какие проблемы в доме?», "
                "«Создай субботник в субботу в 11 у площадки» или «Где ближайшее укрытие?»."
            )
        )
