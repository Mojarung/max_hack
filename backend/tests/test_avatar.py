"""Аватар жителя: своё фото и выбранная картинка стоят выше фото из MAX."""

from domovoy.modules.users.avatar import avatar_choice, avatar_url, preset_avatar
from domovoy.modules.users.models import User

MAX_PHOTO = "https://max.example/photo.jpg"


def user(avatar: str | None, photo_url: str | None = MAX_PHOTO) -> User:
    return User(max_user_id=1, first_name="Анна", avatar=avatar, photo_url=photo_url)


class TestAvatarUrl:
    def test_without_choice_shows_max_photo(self) -> None:
        assert avatar_url(user(None)) == MAX_PHOTO
        assert avatar_choice(user(None)) is None

    def test_without_anything_leaves_choice_to_frontend(self) -> None:
        assert avatar_url(user(None, photo_url=None)) is None

    def test_preset_overrides_max_photo(self) -> None:
        assert avatar_url(user("preset:3")) == preset_avatar(3) == "/avatars/3.webp"
        assert avatar_choice(user("preset:3")) == "preset:3"

    def test_upload_is_served_from_media(self) -> None:
        u = user("upload:avatars/7/abc.jpg")
        assert avatar_url(u) == "/api/v1/media/avatars/7/abc.jpg"
        assert avatar_choice(u) == "upload"

    def test_broken_value_falls_back_to_max_photo(self) -> None:
        for broken in ("preset:0", "preset:10", "preset:x", "something"):
            assert avatar_url(user(broken)) == MAX_PHOTO
            assert avatar_choice(user(broken)) is None
