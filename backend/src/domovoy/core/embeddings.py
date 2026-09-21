"""Эмбеддинги для RAG-поиска.

По умолчанию работает локальный хэширующий эмбеддер: символьные триграммы и слова
раскладываются по фиксированному числу измерений, затем вектор нормируется.
Он не требует сети и GPU, устойчив к опечаткам и падежам («протекает крыша» ≈ «течь кровли»
ловится вместе с синонимами из SYNONYMS). Поиск гибридный: этот вектор (pgvector, косинус)
плюс полнотекстовый индекс Postgres с русской морфологией.
"""

import hashlib
import math
import re

from domovoy.core.config import get_settings

WORD_RE = re.compile(r"[a-zа-яё0-9]+", re.IGNORECASE)

# Небольшой словарь бытовых синонимов, чтобы разные формулировки одной проблемы сближались.
SYNONYMS: dict[str, str] = {
    "кровля": "крыша",
    "протечка": "течь",
    "протекает": "течь",
    "течет": "течь",
    "капает": "течь",
    "заливает": "течь",
    "затопило": "течь",
    "лифт": "лифт",
    "подъемник": "лифт",
    "свет": "освещение",
    "лампочка": "освещение",
    "лампа": "освещение",
    "темно": "освещение",
    "мусор": "мусор",
    "контейнер": "мусор",
    "помойка": "мусор",
    "батарея": "отопление",
    "холодно": "отопление",
    "радиатор": "отопление",
    "яма": "дорога",
    "асфальт": "дорога",
    "субботник": "уборка",
    "уборка": "уборка",
}


def _stem(word: str) -> str:
    word = word.lower().replace("ё", "е")
    if word in SYNONYMS:
        return SYNONYMS[word]
    return word[:6] if len(word) > 6 else word


def _bucket(token: str, dim: int) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    return value % dim, 1.0 if (value >> 63) & 1 else -1.0


def embed(text: str, dim: int | None = None) -> list[float]:
    dim = dim or get_settings().embedding_dim
    vec = [0.0] * dim
    words = [_stem(w) for w in WORD_RE.findall(text)]
    for word in words:
        idx, sign = _bucket(f"w:{word}", dim)
        vec[idx] += 2.0 * sign
        padded = f"#{word}#"
        for i in range(len(padded) - 2):
            idx, sign = _bucket(f"t:{padded[i : i + 3]}", dim)
            vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec))
    if norm == 0:
        return vec
    return [v / norm for v in vec]
