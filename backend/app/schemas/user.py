import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from app.services.phone_verification_service import is_phone_verified


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
    phone_verified: bool = False
    phone_verified_at: datetime.datetime | None = Field(default=None, exclude=True)
    phone_verified_fingerprint: str | None = Field(default=None, exclude=True)
    phone_verified_message_at: datetime.datetime | None = Field(default=None, exclude=True)
    phone_verified_update_id: int | None = Field(default=None, exclude=True)

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def set_phone_verified(self) -> "UserResponse":
        self.phone_verified = is_phone_verified(self)
        return self


class SelfProfileResponse(UserResponse):
    inplace_online_payment_enabled: bool = False


class UserUpdate(BaseModel):
    language: str | None = None

    model_config = {"extra": "forbid"}


class UserRoleUpdate(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"customer", "staff", "admin"}:
            raise ValueError("Invalid role")
        return normalized
