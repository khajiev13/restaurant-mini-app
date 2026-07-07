from pydantic import BaseModel, field_validator


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
    role: str = "customer"

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    phone_number: str | None = None
    language: str | None = None


class UserRoleUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"customer", "staff", "admin"}:
            raise ValueError("Invalid role")
        return normalized
