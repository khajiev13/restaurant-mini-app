import datetime
import uuid

from pydantic import BaseModel


class OrderItemModifier(BaseModel):
    id: str
    quantity: float
    price: float


class OrderItem(BaseModel):
    id: str
    quantity: float
    price: float
    modifications: list[OrderItemModifier] = []


class OrderCreate(BaseModel):
    address_id: uuid.UUID | None = None
    items: list[OrderItem]
    comment: str | None = None
    payment_method: str = "cash"
    discriminator: str = "delivery"
    # For delivery — client info
    phone_number: str
    delivery_address: str | None = None
    latitude: str | None = None
    longitude: str | None = None


class OrderResponse(BaseModel):
    id: uuid.UUID
    items: list[dict]
    total_amount: float
    delivery_fee: float
    comment: str | None = None
    payment_method: str
    discriminator: str
    alipos_order_id: uuid.UUID | None = None
    alipos_eats_id: str | None = None
    status: str
    order_number: str | None = None
    status_updated_at: datetime.datetime | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class OrderStatusResponse(BaseModel):
    status: str
    order_number: str | None = None
    alipos_order_id: uuid.UUID | None = None
