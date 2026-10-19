"""Аватар жителя: готовая картинка, своё фото или фото из MAX.

Выбор жителя хранится в `User.avatar` и стоит выше фото из MAX, которое обновляется при каждом входе.
Готовые картинки лежат во фронтенде (`frontend/public/avatars/N.webp`), поэтому API отдаёт путь от корня сайта.
"""

from domovoy.core.storage import media_url
from domovoy.modules.users.models import User

PRESET_COUNT = 9
PRESET_PREFIX = "preset:"
UPLOAD_PREFIX = "upload:"


def preset_avatar(number: int) -> str:
    return f"/avatars/{number}.webp"


def preset_number(user: User) -> int | None:
    value = user.avatar or ""
    if not value.startswith(PRESET_PREFIX):
        return None
    number = value.removeprefix(PRESET_PREFIX)
    return int(number) if number.isdigit() and 1 <= int(number) <= PRESET_COUNT else None


def uploaded_key(user: User) -> str | None:
    value = user.avatar or ""
    return value.removeprefix(UPLOAD_PREFIX) if value.startswith(UPLOAD_PREFIX) else None


def avatar_url(user: User) -> str | None:
    """Что показывать: своё фото, выбранная картинка, фото из MAX. None - фронтенд подставит картинку по id."""
    key = uploaded_key(user)
    if key:
        return media_url(key)
    number = preset_number(user)
    if number:
        return preset_avatar(number)
    return user.photo_url


def avatar_choice(user: User) -> str | None:
    """Текущий выбор для экрана выбора аватара: «preset:N», «upload» или None (как в MAX)."""
    number = preset_number(user)
    if number:
        return f"{PRESET_PREFIX}{number}"
    return "upload" if uploaded_key(user) else None
