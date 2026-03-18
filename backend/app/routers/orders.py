import datetime
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.models.models import Order
from app.schemas.common import ApiResponse
from app.schemas.order import OrderCreate, OrderResponse, OrderStatusResponse
from app.services import alipos_api

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
    """Place an order: save to DB, send to AliPOS, return confirmation."""
    # Calculate total
    total = sum(
        item.price * item.quantity
        + sum(m.price * m.quantity for m in item.modifications)
        for item in body.items
    )

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
    if body.discriminator == "delivery" and body.delivery_address:
        alipos_payload["deliveryInfo"]["deliveryAddress"] = {
            "full": body.delivery_address,
            "latitude": body.latitude or "",
            "longitude": body.longitude or "",
        }

    # TODO: inplace orders — add tableId when supported

    # Send to AliPOS
    try:
        alipos_resp = await alipos_api.create_order(alipos_payload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to create order in AliPOS: {exc}",
        ) from exc

    alipos_order_id = alipos_resp.get("orderId")

    # Save to DB
    order = Order(
        user_id=current_user.telegram_id,
        address_id=body.address_id,
        items=[item.model_dump() for item in body.items],
        total_amount=total,
        delivery_fee=0,
        comment=body.comment,
        payment_method=body.payment_method,
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
                order.status_updated_at = datetime.datetime.now(datetime.UTC)
                await db.commit()
        except Exception:
            pass  # Return cached status if AliPOS is unreachable

    return ApiResponse(
        success=True,
        data=OrderStatusResponse(
            status=order.status,
            order_number=order.order_number,
            alipos_order_id=order.alipos_order_id,
        ).model_dump(mode="json"),
    )
