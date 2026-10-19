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


# Слова, которые чаще обозначают место, чем саму проблему: решают, только если других совпадений нет
PLACE_WORDS = frozenset({"подъезд", "лестниц"})


def classify_rules(text: str) -> Classification:
    """Газ побеждает всегда (экстренный случай). Остальные: выигрывает категория, упомянутая раньше,
    но слова-места («подъезд») уступают любому совпадению по сути проблемы.

    Житель обычно начинает с сути («Течёт крыша…»), а место и последствия пишет после
    («…лужа в подъезде»), поэтому первое упоминание надёжнее суммы совпадений.
    """
    low = _normalize(text)
    hits: list[tuple[int, int, int, str]] = []
    for cat in CATEGORIES:
        # «в подвале второго подъезда течёт кран»: подъезд здесь место, а не проблема подъезда
        found = [k for k in cat.keywords if k in low]
        strong = [k for k in found if k not in PLACE_WORDS] or found
        positions = [low.find(k) for k in strong]
        if positions:
            weak = all(k in PLACE_WORDS for k in strong)
            hits.append((1 if weak else 0, min(positions), -len(positions), cat.code))
    if not hits:
        return Classification("other", make_title(text), 0.3, "rules")
    if any(code == "gas" for *_, code in hits):
        return Classification("gas", make_title(text), 0.9, "rules")
    hits.sort()
    confidence = 0.8 if len(hits) == 1 else 0.6
    return Classification(hits[0][3], make_title(text), confidence, "rules")


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
