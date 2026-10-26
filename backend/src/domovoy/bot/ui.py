"""Кнопки, страницы списков и форматирование для сообщений Кузи в чате."""

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

# Время в сообщениях Кузи - московское с пометкой «МСК», как в уведомлениях воркера (worker/main.py)
MSK = ZoneInfo("Europe/Moscow")
# не больше пяти позиций на экране: список с кнопками помещается на телефоне без прокрутки
PAGE_SIZE = 5


def button(text: str, payload: str) -> dict[str, str]:
    return {"type": "callback", "text": text, "payload": payload}


def back_row(text: str = "⬅️ Назад в меню", payload: str = "menu:menu") -> list[dict[str, str]]:
    return [button(text, payload)]


def price_text(price: int) -> str:
    return "даром" if price == 0 else f"{price} ₽"


# ---------- страницы списков ----------


@dataclass(frozen=True)
class Page:
    """Страница списка: номер, сколько всего страниц и какие позиции видны (нумерация с 1)."""

    number: int
    pages: int
    first: int
    last: int
    total: int

    @property
    def shown(self) -> str:
        span = f"{self.first}-{self.last}" if self.last > self.first else str(self.first)
        return f"Показано: {span} из {self.total}"

    @property
    def tail(self) -> str:
        """Номер страницы для кнопок со списка: «:2», чтобы «Назад» вернул на ту же страницу."""
        return f":{self.number}" if self.number > 1 else ""


def paginate[T](items: list[T], page: int) -> tuple[list[T], Page]:
    pages = max(1, -(-len(items) // PAGE_SIZE))
    number = min(max(page, 1), pages)
    start = (number - 1) * PAGE_SIZE
    chunk = items[start : start + PAGE_SIZE]
    return chunk, Page(number, pages, start + 1, start + len(chunk), len(items))


def pager_row(page: Page, payload: str) -> list[dict[str, str]]:
    """Стрелки листания: payload списка плюс номер страницы («menu:issues:2»)."""
    row = []
    if page.number > 1:
        row.append(button("◀️ Предыдущие", f"{payload}:{page.number - 1}"))
    if page.number < page.pages:
        row.append(button("Следующие ▶️", f"{payload}:{page.number + 1}"))
    return row


def page_arg(args: list[str], index: int) -> int:
    return int(args[index]) if len(args) > index and args[index].isdigit() else 1


# ---------- форматирование ----------


def fmt_hours(hours: int) -> str:
    if hours < 24:
        return f"{hours} {_plural(hours, 'час', 'часа', 'часов')}"
    days = hours // 24
    return f"{days} {_plural(days, 'сутки', 'суток', 'суток')}" if days < 30 else f"{days} дней"


def fmt_dt(value: datetime) -> str:
    return value.astimezone(MSK).strftime("%d.%m в %H:%M МСК")


def fmt_left(deadline: datetime) -> str:
    left = deadline - datetime.now(UTC)
    hours = int(abs(left).total_seconds() // 3600)
    span = f"{hours} ч" if hours < 48 else f"{hours // 24} дн"
    return f"осталось {span}" if left.total_seconds() > 0 else f"просрочено на {span}"


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many
