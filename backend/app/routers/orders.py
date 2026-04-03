import datetime
import logging
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.models.models import Address, Order
from app.schemas.common import ApiResponse
from app.schemas.order import OrderCreate, OrderResponse, OrderStatusResponse
from app.services import alipos_api
from app.services import multicard_api

logger = logging.getLogger(__name__)

# Payment method IDs (hardcoded across all AliPOS restaurants)
PAYMENT_IDS = {
    "cash": "59FFAC8D-ACE5-4758-8FB7-6C1F69713C37",
    "card": "3C9889C8-1A85-4172-B3BA-0B0C91F05411",
    "rahmat": "C4AAD2B3-8D99-4BD2-9647-8806136556CF",
}

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    body: OrderCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Place an order: save to DB, send to AliPOS, optionally create Multicard invoice."""
    selected_address = None
    delivery_address = body.delivery_address
    latitude = body.latitude
    longitude = body.longitude

    if body.discriminator == "delivery":
        if body.address_id:
            result = await db.execute(
                select(Address).where(
                    Address.id == body.address_id,
                    Address.user_id == current_user.telegram_id,
                )
            )
            selected_address = result.scalar_one_or_none()
            if not selected_address:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Delivery address not found",
                )

            delivery_address = selected_address.full_address
            latitude = selected_address.latitude or latitude
            longitude = selected_address.longitude or longitude

        if not delivery_address:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Delivery address is required",
            )

        if not latitude or not longitude:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Selected delivery address is missing map coordinates. "
                    "Edit the address and use your location before placing the order."
                ),
            )

    # Calculate total
    total = sum(
        item.price * item.quantity
        + sum(m.price * m.quantity for m in item.modifications)
        for item in body.items
    )

    # Pre-generate order UUID so we can use it as Multicard invoice_id before DB insert
    order_id = uuid.uuid4()
    eats_id = f"mrpub-{uuid.uuid4().hex[:12]}"
    payment_id = PAYMENT_IDS.get(body.payment_method, PAYMENT_IDS["cash"])

    # Build AliPOS order payload
    alipos_payload = {
        "discriminator": body.discriminator,
        "platform": "MrPubBot",
        "eatsId": eats_id,
        "restaurantId": settings.alipos_restaurant_id,
        "comment": body.comment or "",
        "deliveryInfo": {
            "clientName": f"{current_user.first_name} {current_user.last_name or ''}".strip(),
            "phoneNumber": body.phone_number,
        },
        "paymentInfo": {
            "paymentId": payment_id,
            "itemsCost": total,
            "total": total,
            "deliveryFee": 0.0,
        },
        "items": [
            {
                "id": item.id,
                "quantity": item.quantity,
                "price": item.price,
                "modifications": [
                    {"id": m.id, "quantity": m.quantity, "price": m.price}
                    for m in item.modifications
                ],
            }
            for item in body.items
        ],
    }

    # Add delivery address for delivery orders
    if body.discriminator == "delivery" and delivery_address:
        alipos_payload["deliveryInfo"]["deliveryAddress"] = {
            "full": delivery_address,
            "latitude": latitude,
            "longitude": longitude,
        }

    # TODO: inplace orders — add tableId when supported

    # Send to AliPOS
    logger.info(
        "Creating AliPOS order: user=%s items=%s total=%s discriminator=%s payment=%s",
        current_user.telegram_id,
        len(body.items),
        total,
        body.discriminator,
        body.payment_method,
    )
    try:
        alipos_resp = await alipos_api.create_order(alipos_payload)
    except Exception as exc:
        logger.exception(
            "AliPOS order creation failed for user=%s eats_id=%s: %s",
            current_user.telegram_id,
            eats_id,
            exc,
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create order in AliPOS: {exc}",
        ) from exc

    alipos_order_id = alipos_resp.get("orderId")

    # Multicard / Rahmat: create invoice and set payment metadata
    multicard_invoice_uuid = None
    multicard_checkout_url = None
    payment_provider = None
    payment_status = None
    payment_expires_at = None

    if body.payment_method == "rahmat":
        # Amounts in tiyin (1 UZS = 100 tiyin)
        amount_tiyin = int(total * 100)
        return_url = settings.telegram_order_deep_link(str(order_id))

        logger.info(
            "Creating Multicard invoice: order=%s amount_tiyin=%s",
            order_id,
            amount_tiyin,
        )
        try:
            invoice_data = await multicard_api.create_invoice(
                amount_tiyin=amount_tiyin,
                invoice_id=str(order_id),
                return_url=return_url,
                ttl=settings.rahmat_payment_timeout_seconds,
            )
        except Exception as exc:
            logger.exception(
                "Multicard invoice creation failed for order=%s: %s",
                order_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to create Multicard invoice: {exc}",
            ) from exc

        multicard_invoice_uuid = invoice_data["uuid"]
        multicard_checkout_url = invoice_data["checkout_url"]
        payment_provider = "multicard"
        payment_status = "pending"
        now = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
        payment_expires_at = now + datetime.timedelta(
            seconds=settings.rahmat_payment_timeout_seconds
        )

    # Save to DB
    order = Order(
        id=order_id,
        user_id=current_user.telegram_id,
        address_id=selected_address.id if selected_address else body.address_id,
        items=[item.model_dump() for item in body.items],
        total_amount=total,
        delivery_fee=0,
        comment=body.comment,
        payment_method=body.payment_method,
        payment_provider=payment_provider,
        payment_status=payment_status,
        payment_expires_at=payment_expires_at,
        multicard_invoice_uuid=multicard_invoice_uuid,
        multicard_checkout_url=multicard_checkout_url,
        discriminator=body.discriminator,
        alipos_order_id=alipos_order_id,
        alipos_eats_id=eats_id,
        status="NEW",
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    return ApiResponse(
        success=True,
        data=OrderResponse.model_validate(order).model_dump(mode="json"),
    )


@router.get("")
async def get_orders(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    """Get current user's order history."""
    result = await db.execute(
        select(Order)
        .where(Order.user_id == current_user.telegram_id)
        .order_by(Order.created_at.desc())
    )
    orders = result.scalars().all()
    return ApiResponse(
        success=True,
        data=[
            OrderResponse.model_validate(o).model_dump(mode="json") for o in orders
        ],
    )


@router.get("/{order_id}")
async def get_order(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Get a single order with its current status."""
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.telegram_id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )
    return ApiResponse(
        success=True,
        data=OrderResponse.model_validate(order).model_dump(mode="json"),
    )


@router.get("/{order_id}/status")
async def get_order_status(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Poll AliPOS for the latest order status."""
    result = await db.execute(
        select(Order).where(
            Order.id == order_id,
            Order.user_id == current_user.telegram_id,
        )
    )
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Order not found"
        )

    if order.alipos_order_id:
        try:
            alipos_data = await alipos_api.get_order_status(
                str(order.alipos_order_id)
            )
            new_status = alipos_data.get("status", order.status)
            order_number = alipos_data.get("orderNumber")
            if new_status != order.status or order_number != order.order_number:
                order.status = new_status
                order.order_number = order_number
                order.status_updated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
                await db.commit()
        except Exception:
            pass  # Return cached status if AliPOS is unreachable

    return ApiResponse(
        success=True,
        data=OrderStatusResponse(
            status=order.status,
            order_number=order.order_number,
            alipos_order_id=order.alipos_order_id,
            payment_status=order.payment_status,
            payment_expires_at=order.payment_expires_at,
            multicard_receipt_url=order.multicard_receipt_url,
        ).model_dump(mode="json"),
    )
