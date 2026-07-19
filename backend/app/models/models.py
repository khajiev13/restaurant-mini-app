import datetime
import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    telegram_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    first_name: Mapped[str] = mapped_column(String(255))
    last_name: Mapped[str | None] = mapped_column(String(255))
    username: Mapped[str | None] = mapped_column(String(255))
    phone_number: Mapped[str | None] = mapped_column(String(50))
    phone_verified_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    phone_verified_fingerprint: Mapped[str | None] = mapped_column(String(64))
    phone_verified_message_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True))
    phone_verified_update_id: Mapped[int | None] = mapped_column(BigInteger)
    language: Mapped[str] = mapped_column(String(5), default="uz")
    role: Mapped[str] = mapped_column(String(32), default="customer")
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )

    addresses: Mapped[list["Address"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        foreign_keys="Order.user_id",
    )
    assigned_orders: Mapped[list["Order"]] = relationship(
        back_populates="assigned_staff",
        foreign_keys="Order.assigned_staff_id",
    )

    __table_args__ = (
        CheckConstraint("role IN ('customer', 'staff', 'admin')", name="ck_users_role_valid"),
    )


class Address(Base):
    __tablename__ = "addresses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(100), default="Home")
    full_address: Mapped[str] = mapped_column(Text)
    latitude: Mapped[str | None] = mapped_column(String(30))
    longitude: Mapped[str | None] = mapped_column(String(30))
    entrance: Mapped[str | None] = mapped_column(String(50))
    apartment: Mapped[str | None] = mapped_column(String(50))
    floor: Mapped[str | None] = mapped_column(String(20))
    door_code: Mapped[str | None] = mapped_column(String(50))
    courier_instructions: Mapped[str | None] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )

    user: Mapped["User"] = relationship(back_populates="addresses")

    __table_args__ = (Index("idx_addresses_user_id", "user_id"),)


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.telegram_id", ondelete="CASCADE"))
    client_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    address_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id", ondelete="SET NULL")
    )
    assigned_staff_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="SET NULL"),
    )
    assigned_at: Mapped[datetime.datetime | None] = mapped_column()
    delivered_at: Mapped[datetime.datetime | None] = mapped_column()
    items: Mapped[dict] = mapped_column(JSONB)
    delivery_info: Mapped[dict | None] = mapped_column(JSONB)
    items_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    delivery_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    comment: Mapped[str | None] = mapped_column(Text)
    contact_phone_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=text("false"),
    )
    payment_method: Mapped[str] = mapped_column(String(100), default="cash")
    payment_provider: Mapped[str | None] = mapped_column(String(50))
    payment_status: Mapped[str | None] = mapped_column(String(50))
    payment_expires_at: Mapped[datetime.datetime | None] = mapped_column()
    payment_paid_at: Mapped[datetime.datetime | None] = mapped_column()
    payment_error: Mapped[str | None] = mapped_column(Text)
    payment_card_pan: Mapped[str | None] = mapped_column(String(32))
    payment_ps: Mapped[str | None] = mapped_column(String(50))
    discriminator: Mapped[str] = mapped_column(String(20), default="delivery")
    table_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    table_title: Mapped[str | None] = mapped_column(String(100))
    hall_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    hall_title: Mapped[str | None] = mapped_column(String(100))
    service_percent: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    table_access_expires_at: Mapped[datetime.datetime | None] = mapped_column()
    alipos_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    alipos_eats_id: Mapped[str | None] = mapped_column(String(255))
    alipos_sync_status: Mapped[str | None] = mapped_column(String(32))
    alipos_sync_error: Mapped[str | None] = mapped_column(Text)
    multicard_invoice_uuid: Mapped[str | None] = mapped_column(String(64))
    multicard_checkout_url: Mapped[str | None] = mapped_column(Text)
    multicard_receipt_url: Mapped[str | None] = mapped_column(Text)
    multicard_payment_uuid: Mapped[str | None] = mapped_column(String(64))
    invoice_cancel_status: Mapped[str | None] = mapped_column(String(32))
    refund_sync_status: Mapped[str | None] = mapped_column(String(32))
    refund_sync_error: Mapped[str | None] = mapped_column(Text)
    alipos_cancel_status: Mapped[str | None] = mapped_column(String(50))
    alipos_cancel_error: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="NEW")
    order_number: Mapped[str | None] = mapped_column(String(50))
    status_updated_at: Mapped[datetime.datetime | None] = mapped_column()
    alipos_status_updated_at: Mapped[datetime.datetime | None] = mapped_column()
    alipos_status_check_attempted_at: Mapped[datetime.datetime | None] = mapped_column()
    alipos_status_checked_at: Mapped[datetime.datetime | None] = mapped_column()
    cancel_requested_at: Mapped[datetime.datetime | None] = mapped_column()
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )

    user: Mapped["User"] = relationship(
        back_populates="orders",
        foreign_keys=[user_id],
    )
    assigned_staff: Mapped["User | None"] = relationship(
        back_populates="assigned_orders",
        foreign_keys=[assigned_staff_id],
    )
    address: Mapped["Address | None"] = relationship()

    __table_args__ = (
        Index("idx_orders_user_id", "user_id"),
        Index(
            "uq_orders_user_request",
            "user_id",
            "client_request_id",
            unique=True,
            postgresql_where=text("client_request_id IS NOT NULL"),
        ),
        Index("idx_orders_alipos_order_id", "alipos_order_id"),
        Index("idx_orders_alipos_eats_id", "alipos_eats_id"),
        Index("idx_orders_table_id", "table_id"),
        Index("idx_orders_alipos_sync_status", "alipos_sync_status"),
        Index(
            "idx_orders_inplace_workspace",
            "table_id",
            "alipos_sync_status",
            "status",
            "alipos_status_check_attempted_at",
            postgresql_where=text("discriminator = 'inplace'"),
        ),
        Index("idx_orders_payment_status", "payment_status"),
        Index("idx_orders_payment_expires_at", "payment_expires_at"),
        Index("idx_orders_multicard_payment_uuid", "multicard_payment_uuid"),
        Index("idx_orders_refund_sync_status", "refund_sync_status"),
        Index("idx_orders_assigned_staff_id", "assigned_staff_id"),
        Index("idx_orders_delivered_at", "delivered_at"),
        Index("idx_orders_staff_available", "status", "assigned_staff_id", "discriminator"),
        Index(
            "uq_orders_one_active_delivery_per_staff",
            "assigned_staff_id",
            unique=True,
            postgresql_where=text(
                "assigned_staff_id IS NOT NULL "
                "AND discriminator = 'delivery' "
                "AND delivered_at IS NULL "
                "AND status NOT IN ('DELIVERED', 'CANCELLED', 'CANCELED')"
            ),
        ),
    )


class Stoplist(Base):
    __tablename__ = "stoplist"

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    restaurant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    count: Mapped[int] = mapped_column(default=-1)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )
