import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class OrderItemModifier(BaseModel):
    id: str
    name: str | None = None
    quantity: float = Field(ge=0.01, le=100)
    price: float


class OrderItem(BaseModel):
    id: str
    name: str | None = None
    quantity: float = Field(ge=0.01, le=100)
    price: float
    modifications: list[OrderItemModifier] = Field(default_factory=list)


class OrderCreate(BaseModel):
    model_config = {"extra": "forbid"}

    client_request_id: uuid.UUID | None = None
    address_id: uuid.UUID | None = None
    items: list[OrderItem]
    comment: str | None = Field(default=None, max_length=200)
    payment_method: Literal["cash", "rahmat"] = "cash"
    discriminator: Literal["delivery", "inplace"] = "delivery"
    table_access_token: str | None = None
    delivery_address: str | None = None
    latitude: str | None = None
    longitude: str | None = None

    @model_validator(mode="after")
    def validate_order_context(self):
        if self.discriminator == "inplace" and not self.table_access_token:
            raise ValueError("Table access token is required for an inplace order")
        return self


class OrderResponse(BaseModel):
    id: uuid.UUID
    items: list[dict]
    items_cost: float
    total_amount: float
    delivery_fee: float
    comment: str | None = None
    payment_method: str
    payment_provider: str | None = None
    payment_status: str | None = None
    payment_expires_at: datetime.datetime | None = None
    multicard_checkout_url: str | None = None
    multicard_receipt_url: str | None = None
    discriminator: str
    table_title: str | None = None
    hall_title: str | None = None
    service_percent: float = 0
    alipos_sync_status: str | None = None
    status: str
    order_number: str | None = None
    status_updated_at: datetime.datetime | None = None
    created_at: datetime.datetime

    model_config = {"from_attributes": True}


class OrderStatusResponse(BaseModel):
    status: str
    order_number: str | None = None
    payment_status: str | None = None
    payment_expires_at: datetime.datetime | None = None
    multicard_receipt_url: str | None = None
    table_title: str | None = None
    hall_title: str | None = None
    service_percent: float = 0
    alipos_sync_status: str | None = None


class StaffCustomerResponse(BaseModel):
    telegram_id: int
    first_name: str
    last_name: str | None = None
    phone_number: str | None = None


class StaffAddressResponse(BaseModel):
    full_address: str
    latitude: str | None = None
    longitude: str | None = None
    entrance: str | None = None
    apartment: str | None = None
    floor: str | None = None
    courier_instructions: str | None = None


class StaffSummaryResponse(BaseModel):
    telegram_id: int
    first_name: str
    last_name: str | None = None


class StaffOrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str | None = None
    status: str
    created_at: datetime.datetime
    status_updated_at: datetime.datetime | None = None
    assigned_at: datetime.datetime | None = None
    delivered_at: datetime.datetime | None = None
    customer: StaffCustomerResponse
    address: StaffAddressResponse
    items: list[dict]
    total_amount: float
    delivery_fee: float
    payment_method: str
    payment_status: str | None = None
    assigned_staff: StaffSummaryResponse | None = None


def build_staff_order_response(order) -> StaffOrderResponse:
    address = order.address
    assigned_staff = order.assigned_staff
    customer_phone = order.user.phone_number
    if order.contact_phone_verified:
        delivery_info = (
            order.delivery_info if isinstance(order.delivery_info, dict) else {}
        )
        snapshot_phone = delivery_info.get("phoneNumber")
        customer_phone = snapshot_phone if isinstance(snapshot_phone, str) else None

    return StaffOrderResponse(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        created_at=order.created_at,
        status_updated_at=order.status_updated_at,
        assigned_at=order.assigned_at,
        delivered_at=order.delivered_at,
        customer=StaffCustomerResponse(
            telegram_id=order.user.telegram_id,
            first_name=order.user.first_name,
            last_name=order.user.last_name,
            phone_number=customer_phone,
        ),
        address=StaffAddressResponse(
            full_address=address.full_address if address else "",
            latitude=address.latitude if address else None,
            longitude=address.longitude if address else None,
            entrance=address.entrance if address else None,
            apartment=address.apartment if address else None,
            floor=address.floor if address else None,
            courier_instructions=address.courier_instructions if address else None,
        ),
        items=order.items,
        total_amount=float(order.total_amount),
        delivery_fee=float(order.delivery_fee),
        payment_method=order.payment_method,
        payment_status=order.payment_status,
        assigned_staff=(
            StaffSummaryResponse(
                telegram_id=assigned_staff.telegram_id,
                first_name=assigned_staff.first_name,
                last_name=assigned_staff.last_name,
            )
            if assigned_staff
            else None
        ),
    )
