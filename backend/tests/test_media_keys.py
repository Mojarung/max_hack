"""Эндпоинт /media отдаёт все ключи, которые сохраняет хранилище, и ничего лишнего."""

import pytest

from domovoy.api.system import KEY_RE

HEX = "0123456789abcdef0123456789abcdef"


@pytest.mark.parametrize(
    "key",
    [
        f"issues/{HEX}.jpg",
        f"listings/{HEX}.jpg",
        f"issues/12/{HEX}.jpg",
        f"avatars/7/{HEX}.jpg",
        f"demo/{HEX}.jpg",
        f"events/{HEX}.jpg",
    ],
)
def test_saved_keys_are_served(key: str) -> None:
    assert KEY_RE.match(key)


@pytest.mark.parametrize(
    "key",
    [f"documents/{HEX}.jpg", f"issues/../{HEX}.jpg", f"issues/{HEX}.png", "issues/abc.jpg", f"avatars/x/{HEX}.jpg"],
)
def test_other_keys_are_rejected(key: str) -> None:
    assert not KEY_RE.match(key)
