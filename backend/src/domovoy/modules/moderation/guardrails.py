"""Гардрейлы модерации: мат, оскорбления, реклама и спам.

Два слоя. Первый: быстрые детерминированные правила (регулярки с нормализацией обфускации
вида «х у й», «xyй», «п*зд»). Второй, опционально: LLM-проверка вежливости, если подключена
настоящая модель. LLM работает по принципу fail-open: сбой модели не блокирует сообщение.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

import structlog
from pydantic import BaseModel

from domovoy.agent.llm import get_llm, is_real_llm

log = structlog.get_logger(__name__)

Verdict = Literal["ok", "warn", "block"]

LOOKALIKE = str.maketrans(
    {
        "a": "а",
        "e": "е",
        "o": "о",
        "p": "р",
        "c": "с",
        "x": "х",
        "y": "у",
        "k": "к",
        "m": "м",
        "t": "т",
        "b": "в",
        "h": "н",
        "u": "и",
        "3": "з",
        "0": "о",
        "@": "а",
        "6": "б",
        "ё": "е",
    }
)
# «х у й», «х.у.й»: цепочка одиночных букв через разделители склеивается в слово
SPACED_LETTERS = re.compile(r"(?<![а-яa-z])(?:[а-яa-z][\s._\-]+){2,}[а-яa-z](?![а-яa-z])")
MASK = re.compile(r"(?<=[а-я])[*#$%]+(?=[а-я])")

PROFANITY = re.compile(
    r"(?<![а-я])(?:за|на|по|от|у|вы|до|раз|при|об|пере|под|ни)?"
    r"(?:ху[йеияюл]|п[ие]?зд|еб[аулиоы]|ебн|бля|муда|мудил|гандон|шлюх|пидо?р|пидар|залуп|манда)",
)
INSULTS = re.compile(
    r"(?<![а-я])(?:дурак|дура\b|идиот|дебил|тупиц|тупой|тупая|урод|козел|козл|кретин|придур|скотин|"
    r"мраз|твар|чмо|лох|заткнис|овц[аы]|быдл|сук[аи]\b|гнид)"
)
COMMERCIAL = re.compile(
    r"(?:заработ|доход|пассивн|крипт|ставк|казино|букмек|инвест|скидк|промокод|подработк|"
    r"пиши(?:те)? в лич|в директ|в лс\b|бесплатн[а-я]* консульт|кредит|займ|раскрутк|подписывайтесь)"
)
LINK = re.compile(r"(?:https?://|t\.me/|wa\.me/|bit\.ly|vk\.cc|clck\.ru|@[a-z0-9_]{4,})", re.IGNORECASE)
PHONE = re.compile(r"(?:\+7|8)[\s\-(]*\d{3}[\s\-)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}")


@dataclass(slots=True)
class ModerationResult:
    verdict: Verdict
    reasons: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.verdict == "block"

    def human_reason(self) -> str:
        return ", ".join(self.reasons) or "нарушение правил чата"


MASK_FILL = ("", "у", "и", "е", "а")


def normalize(text: str) -> list[str]:
    """Варианты нормализованного текста: маска «*» перебирается гласными («нах*й» → «нахуй»)."""
    low = text.lower().translate(LOOKALIKE)
    low = SPACED_LETTERS.sub(lambda m: re.sub(r"[\s._\-]", "", m.group(0)), low)
    if not MASK.search(low):
        return [low]
    return [MASK.sub(fill, low) for fill in MASK_FILL]


def check_rules(text: str) -> ModerationResult:
    variants = normalize(text)
    reasons: list[str] = []
    if any(PROFANITY.search(v) for v in variants):
        reasons.append("нецензурная лексика")
    if any(INSULTS.search(v) for v in variants):
        reasons.append("оскорбление")
    commercial = len(COMMERCIAL.findall(variants[0]))
    contact = bool(LINK.search(text) or PHONE.search(text))
    if commercial >= 2 or (commercial >= 1 and contact):
        reasons.append("реклама или спам")
    if reasons:
        return ModerationResult("block", reasons)
    letters = [c for c in text if c.isalpha()]
    if len(letters) > 15 and sum(c.isupper() for c in letters) / len(letters) > 0.7:
        return ModerationResult("warn", ["сообщение капсом"])
    return ModerationResult("ok")


class LlmVerdict(BaseModel):
    toxic: bool
    reason: str


LLM_PROMPT = """Ты модератор домового чата. Оцени, есть ли в сообщении грубость, оскорбление соседа,
травля, угрозы или скрытая реклама. Обычная критика УК и эмоции без оскорблений допустимы.
Сообщение: «{text}»"""


async def moderate(text: str) -> ModerationResult:
    result = check_rules(text)
    if result.blocked or not is_real_llm() or len(text) < 25:
        return result
    try:
        verdict = await get_llm().with_structured_output(LlmVerdict).ainvoke(LLM_PROMPT.format(text=text[:1500]))
        if isinstance(verdict, LlmVerdict) and verdict.toxic:
            return ModerationResult("block", [verdict.reason or "невежливое сообщение"])
    except Exception:
        log.warning("moderation.llm_failed", exc_info=True)
    return result
