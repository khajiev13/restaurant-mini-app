import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, Field

StaffTableSyncState = Literal["synchronized", "processing", "attention"]
StaffTablePaymentMethod = Literal["cash", "online"]
StaffTablePaymentStatus = Literal["paid"]
StaffTableSyncLabel = Literal[
    "synchronized",
    "processing",
    "not_synchronized",
    "verify_in_pos",
]


class StaffTableModifierResponse(BaseModel):
    id: str
    name: str | None = None
    quantity: float
    price: float


class StaffTableOrderItemResponse(BaseModel):
    id: str
    name: str | None = None
    quantity: float
    price: float
    modifications: list[StaffTableModifierResponse] = Field(default_factory=list)


class StaffTableItemResponse(StaffTableOrderItemResponse):
    line_total: float


class StaffTableOrderResponse(BaseModel):
    id: uuid.UUID
    order_number: str | None = None
    created_at: datetime.datetime
    status: str
    sync_state: StaffTableSyncState
    sync_label: StaffTableSyncLabel
    payment_method: StaffTablePaymentMethod
    payment_status: StaffTablePaymentStatus | None = None
    items: list[StaffTableOrderItemResponse]
    items_cost: float
    service_amount: float
    total_amount: float


class StaffTableSummaryResponse(BaseModel):
    table_id: uuid.UUID
    table_title: str
    hall_id: uuid.UUID | None = None
    hall_title: str | None = None
    service_percent: float
    is_listed: bool
    synchronized_order_count: int
    processing_order_count: int
    attention_order_count: int
    combined_item_count: float
    combined_line_count: int
    combined_items: list[StaffTableItemResponse]
    items_cost: float
    service_amount: float
    total_amount: float


class StaffHallResponse(BaseModel):
    hall_id: uuid.UUID | None = None
    hall_title: str | None = None
    service_percent: float | None = None
    is_listed: bool
    tables: list[StaffTableSummaryResponse]


class StaffTablesFreshnessResponse(BaseModel):
    generated_at: datetime.datetime
    directory_stale: bool
    directory_last_success_at: datetime.datetime
    order_status_stale: bool
    order_status_oldest_success_at: datetime.datetime | None = None


class StaffTablesOverviewResponse(BaseModel):
    freshness: StaffTablesFreshnessResponse
    halls: list[StaffHallResponse]


class StaffTableDetailResponse(BaseModel):
    freshness: StaffTablesFreshnessResponse
    table: StaffTableSummaryResponse
    orders: list[StaffTableOrderResponse]
