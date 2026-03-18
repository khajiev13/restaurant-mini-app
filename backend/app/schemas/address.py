import uuid

from pydantic import BaseModel


class AddressCreate(BaseModel):
    label: str = "Home"
    full_address: str
    latitude: str | None = None
    longitude: str | None = None
    is_default: bool = False


class AddressResponse(BaseModel):
    id: uuid.UUID
    label: str
    full_address: str
    latitude: str | None = None
    longitude: str | None = None
    is_default: bool

    model_config = {"from_attributes": True}
