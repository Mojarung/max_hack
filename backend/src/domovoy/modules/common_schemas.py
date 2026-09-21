from pydantic import BaseModel

from domovoy.modules.users.models import User


class UserShort(BaseModel):
    id: int
    max_user_id: int
    first_name: str
    last_name: str
    photo_url: str | None
    apartment: str | None

    @classmethod
    def of(cls, user: User) -> "UserShort":
        return cls(
            id=user.id,
            max_user_id=user.max_user_id,
            first_name=user.first_name,
            last_name=user.last_name,
            photo_url=user.photo_url,
            apartment=user.apartment,
        )


class Ok(BaseModel):
    ok: bool = True
