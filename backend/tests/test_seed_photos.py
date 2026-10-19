"""Фото демо-данных: каждая заявка и вещь из сида находит свои картинки по заголовку."""

from domovoy.seed import DEMO_PHOTOS, _photo_names


def test_photo_names_match_by_title_prefix() -> None:
    assert _photo_names("Течёт крыша над 9 этажом") == ["roof-drip", "roof-stain"]
    assert _photo_names("Детская коляска") == ["stroller", "stroller-2", "stroller-3"]


def test_unknown_title_gets_no_photos() -> None:
    assert _photo_names("Сломан домофон в подъезде") == []


def test_every_listing_has_a_cover_first() -> None:
    assert all(names for names in DEMO_PHOTOS.values())
