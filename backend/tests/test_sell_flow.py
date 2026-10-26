"""Объявление из одного сообщения: название, описание, цена и раздел; страницы списков в чате."""

import pytest

from domovoy.bot import sell_flow, ui


@pytest.mark.parametrize(
    ("text", "title", "description", "price", "category"),
    [
        ("Детская коляска, почти новая, 3000 ₽", "Детская коляска", "Почти новая", 3000, "kids"),
        ("Отдам даром книги для школьников", "Книги для школьников", "", 0, "kids"),
        ("Книги для школьников, даром", "Книги для школьников", "", 0, "kids"),
        ("Шкаф-купе 3000", "Шкаф-купе", "", 3000, "furniture"),
        ("Продам дрель за 1 500", "Дрель", "", 1500, "tools"),
        ("Рассада помидоров 150 руб, сорт Бычье сердце", "Рассада помидоров", "Сорт Бычье сердце", 150, "plants"),
        ("Пылесос\nработает, забирать с 5 этажа", "Пылесос", "Работает, забирать с 5 этажа", None, "electronics"),
        ("iPhone 12 в хорошем состоянии", "IPhone 12 в хорошем состоянии", "", None, "other"),
    ],
)
def test_parse_listing_message(text: str, title: str, description: str, price: int | None, category: str) -> None:
    item = sell_flow.parse(text)
    assert (item.title, item.description, item.price, item.category) == (title, description, price, category)


def test_parse_keeps_long_title_short() -> None:
    item = sell_flow.parse("Очень " * 30)
    assert 3 <= len(item.title) <= sell_flow.TITLE_MAX


@pytest.mark.parametrize(
    ("total", "page", "shown", "first_ids", "arrows"),
    [
        (3, 1, "Показано: 1-3 из 3", [0, 1, 2], []),
        (1, 1, "Показано: 1 из 1", [0], []),
        (12, 1, "Показано: 1-5 из 12", [0, 1, 2, 3, 4], ["list:2"]),
        (12, 2, "Показано: 6-10 из 12", [5, 6, 7, 8, 9], ["list:1", "list:3"]),
        (12, 3, "Показано: 11-12 из 12", [10, 11], ["list:2"]),
        (12, 99, "Показано: 11-12 из 12", [10, 11], ["list:2"]),
        (12, 0, "Показано: 1-5 из 12", [0, 1, 2, 3, 4], ["list:2"]),
    ],
)
def test_pages_of_five_with_arrows(total: int, page: int, shown: str, first_ids: list[int], arrows: list[str]) -> None:
    items, pg = ui.paginate(list(range(total)), page)
    assert items == first_ids and pg.shown == shown
    assert [b["payload"] for b in ui.pager_row(pg, "list")] == arrows
    assert pg.tail == ("" if pg.number == 1 else f":{pg.number}")


def test_page_arg_reads_page_number() -> None:
    assert ui.page_arg(["issues", "3"], 1) == 3
    assert ui.page_arg(["issues"], 1) == 1
    assert ui.page_arg(["issues", "x"], 1) == 1
