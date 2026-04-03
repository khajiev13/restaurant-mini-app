import datetime
import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Numeric, String, Text
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
    language: Mapped[str] = mapped_column(String(5), default="uz")
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )

    addresses: Mapped[list["Address"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="user", cascade="all, delete-orphan")


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
    address_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("addresses.id", ondelete="SET NULL")
    )
    items: Mapped[dict] = mapped_column(JSONB)
    total_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    delivery_fee: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    comment: Mapped[str | None] = mapped_column(Text)
    payment_method: Mapped[str] = mapped_column(String(100), default="cash")
    payment_provider: Mapped[str | None] = mapped_column(String(50))
    payment_status: Mapped[str | None] = mapped_column(String(50))
    payment_expires_at: Mapped[datetime.datetime | None] = mapped_column()
    payment_paid_at: Mapped[datetime.datetime | None] = mapped_column()
    payment_error: Mapped[str | None] = mapped_column(Text)
    payment_card_pan: Mapped[str | None] = mapped_column(String(32))
    payment_ps: Mapped[str | None] = mapped_column(String(50))
    discriminator: Mapped[str] = mapped_column(String(20), default="delivery")
    alipos_order_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    alipos_eats_id: Mapped[str | None] = mapped_column(String(255))
    multicard_invoice_uuid: Mapped[str | None] = mapped_column(String(64))
    multicard_checkout_url: Mapped[str | None] = mapped_column(Text)
    multicard_receipt_url: Mapped[str | None] = mapped_column(Text)
    multicard_payment_uuid: Mapped[str | None] = mapped_column(String(64))
    alipos_cancel_status: Mapped[str | None] = mapped_column(String(50))
    alipos_cancel_error: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="NEW")
    order_number: Mapped[str | None] = mapped_column(String(50))
    status_updated_at: Mapped[datetime.datetime | None] = mapped_column()
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.datetime.now(datetime.UTC).replace(tzinfo=None),
    )

    user: Mapped["User"] = relationship(back_populates="orders")

    __table_args__ = (
        Index("idx_orders_user_id", "user_id"),
        Index("idx_orders_alipos_order_id", "alipos_order_id"),
        Index("idx_orders_alipos_eats_id", "alipos_eats_id"),
        Index("idx_orders_payment_status", "payment_status"),
        Index("idx_orders_payment_expires_at", "payment_expires_at"),
        Index("idx_orders_multicard_payment_uuid", "multicard_payment_uuid"),
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
