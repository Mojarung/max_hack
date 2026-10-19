"""Описание и фото события меняет только организатор или администратор дома."""

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import HTTPException

from domovoy.modules.events.service import check_can_edit


def _event(author_id: int) -> Any:
    return cast(Any, SimpleNamespace(author_id=author_id))


def _user(user_id: int) -> Any:
    return cast(Any, SimpleNamespace(id=user_id))


def test_author_can_edit() -> None:
    check_can_edit(_event(1), _user(1), is_admin=False)


def test_admin_can_edit_foreign_event() -> None:
    check_can_edit(_event(1), _user(2), is_admin=True)


def test_neighbour_cannot_edit() -> None:
    with pytest.raises(HTTPException) as err:
        check_can_edit(_event(1), _user(2), is_admin=False)
    assert err.value.status_code == 403
