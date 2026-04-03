from pydantic import BaseModel


class TelegramAuthRequest(BaseModel):
    init_data: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    telegram_id: int
    first_name: str
    last_name: str | None = None
    username: str | None = None
    phone_number: str | None = None
    language: str = "uz"

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    phone_number: str | None = None
    language: str | None = None
