"""Разбор времени события из русской фразы: «в субботу в 11», «завтра в 18:30», «25.10 в 10»."""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Moscow")

# \b отсекает «субботник» и похожие слова, которые начинаются с названия дня
WEEKDAYS = (
    (re.compile(r"\bпонедельник\b"), 0),
    (re.compile(r"\bвторник\b"), 1),
    (re.compile(r"\bсред[аеуы]\b"), 2),
    (re.compile(r"\bчетверг\b"), 3),
    (re.compile(r"\bпятниц[аеуы]\b"), 4),
    (re.compile(r"\bсуббот[аеуы]\b"), 5),
    (re.compile(r"\bвоскресень[еяю]\b"), 6),
)
TIME_RE = re.compile(r"\bв\s*(\d{1,2})(?:[:.](\d{2}))?\s*(?:час|ч\b|утра|вечера|дня)?")
DATE_RE = re.compile(r"\b(\d{1,2})\.(\d{1,2})(?:\.(\d{2,4}))?\b")
DEFAULT_HOUR = 11


def _time_of(text: str) -> tuple[int, int]:
    for match in TIME_RE.finditer(text):
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        tail = text[match.start() : match.end() + 8]
        if ("вечер" in tail and hour < 12) or ("дня" in tail and hour <= 6):
            hour += 12
        if 0 <= hour < 24 and 0 <= minute < 60:
            return hour, minute
    return DEFAULT_HOUR, 0


def parse_when(text: str, now: datetime | None = None) -> datetime | None:
    """Возвращает дату/время события в часовом поясе Москвы или None, если дату не нашли."""
    now = (now or datetime.now(TZ)).astimezone(TZ)
    low = text.lower().replace("ё", "е")
    try:
        return datetime.fromisoformat(text.strip()).astimezone(TZ)
    except ValueError:
        pass

    day: datetime | None = None
    if "послезавтра" in low:
        day = now + timedelta(days=2)
    elif "завтра" in low:
        day = now + timedelta(days=1)
    elif "сегодня" in low:
        day = now
    else:
        for pattern, weekday in WEEKDAYS:
            if pattern.search(low):
                delta = (weekday - now.weekday()) % 7 or 7
                day = now + timedelta(days=delta)
                break
    if day is None and (m := DATE_RE.search(low)):
        d, mo = int(m.group(1)), int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        if year < 100:
            year += 2000
        try:
            day = now.replace(year=year, month=mo, day=d)
        except ValueError:
            return None
        if day.date() < now.date() and not m.group(3):
            day = day.replace(year=year + 1)
    if day is None:
        return None
    hour, minute = _time_of(low)
    return day.replace(hour=hour, minute=minute, second=0, microsecond=0)
