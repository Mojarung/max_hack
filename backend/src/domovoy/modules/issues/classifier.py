"""Классификация проблемы: LLM со структурированным ответом, при сбое правила по ключевым словам."""

import re
from dataclasses import dataclass
from typing import Literal

import structlog
from pydantic import BaseModel, Field

from domovoy.agent.llm import get_llm, is_real_llm
from domovoy.modules.issues.catalog import CATEGORIES, category

log = structlog.get_logger(__name__)

CategoryCode = Literal[
    "gas", "roof", "water", "heating", "elevator", "electricity", "entrance", "yard", "garbage", "road", "other"
]


class LlmClassification(BaseModel):
    category: CategoryCode = Field(description="Код категории проблемы")
    title: str = Field(description="Короткий заголовок проблемы, до 70 символов, без точки в конце")
    confidence: float = Field(ge=0, le=1, description="Уверенность от 0 до 1")


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    title: str
    confidence: float
    source: str


def _normalize(text: str) -> str:
    return text.lower().replace("ё", "е")


def make_title(text: str) -> str:
    first = re.split(r"(?<=[.!?\n])\s", text.strip(), maxsplit=1)[0].strip(" .!?\n")
    if len(first) > 70:
        first = first[:67].rsplit(" ", 1)[0] + "..."
    return first[:1].upper() + first[1:] if first else "Проблема в доме"


def classify_rules(text: str) -> Classification:
    low = _normalize(text)
    best, best_score = "other", 0
    for cat in CATEGORIES:
        score = sum(len(k) for k in cat.keywords if k in low)
        if score > best_score:
            best, best_score = cat.code, score
    confidence = min(0.9, 0.4 + best_score / 30) if best_score else 0.3
    return Classification(best, make_title(text), round(confidence, 2), "rules")


PROMPT = """Ты классифицируешь обращения жителей многоквартирного дома.
Категории: {cats}.
Выбери одну категорию и придумай короткий заголовок. Текст жителя:
---
{text}
---"""


async def classify(text: str) -> Classification:
    rules = classify_rules(text)
    if not is_real_llm():
        return rules
    # газ определяем правилами всегда: это экстренный случай, ошибка модели недопустима
    if rules.category == "gas":
        return rules
    cats = "; ".join(f"{c.code} - {c.title}" for c in CATEGORIES)
    try:
        model = get_llm().with_structured_output(LlmClassification)
        result = await model.ainvoke(PROMPT.format(cats=cats, text=text[:2000]))
        assert isinstance(result, LlmClassification)
        return Classification(category(result.category).code, result.title[:120], result.confidence, "llm")
    except Exception:
        log.warning("classifier.llm_failed", exc_info=True)
        return rules
