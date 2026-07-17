import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.models.models import Order
from app.schemas.common import ApiResponse
from app.schemas.order import OrderCreate, OrderResponse, OrderStatusResponse
from app.services import alipos_api
from app.services.menu_catalog_service import CartConflict
from app.services.order_service import (
    CancellationConflict,
    CancellationError,
    CustomerOrderError,
    CustomerOrderNotFound,
    OrderSubmissionInProgress,
    OrderSubmissionRejected,
    PaymentCheckoutError,
    PaymentRetryConflict,
    PaymentSwitchConflict,
    PaymentSwitchError,
    cancel_customer_order,
    create_customer_order,
    retry_customer_order_payment,
    switch_customer_order_to_cash,
)
from app.services.order_status_service import apply_alipos_status_update_for_order
from app.services.table_access_service import InvalidTableEntry

router = APIRouter(prefix="/orders", tags=["orders"])
ORDER_SUBMISSION_ERROR_DETAIL = "Could not submit the order to the restaurant"


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_order(
    body: OrderCreate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Create a server-priced delivery or table order."""
    try:
        order = await create_customer_order(db, current_user, body)
    except CartConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "cart_conflict", "changes": exc.changes},
        ) from exc
    except (CustomerOrderError, InvalidTableEntry) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except OrderSubmissionInProgress as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "order_id": str(exc.order_id),
                "status": exc.sync_status,
            },
        ) from exc
    except OrderSubmissionRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ORDER_SUBMISSION_ERROR_DETAIL,
        ) from exc
    except PaymentCheckoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc

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
        data=[OrderResponse.model_validate(o).model_dump(mode="json") for o in orders],
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


@router.delete("/{order_id}")
async def cancel_order(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    try:
        order = await cancel_customer_order(db, current_user, order_id)
    except CustomerOrderNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except CancellationConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except CancellationError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
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
            alipos_data = await alipos_api.get_order_status(str(order.alipos_order_id))
            new_status = alipos_data.get("status", order.status)
            order_number = alipos_data.get("orderNumber")
            if await apply_alipos_status_update_for_order(
                db, order, new_status, order_number
            ):
                await db.commit()
        except Exception:
            pass  # Return cached status if AliPOS is unreachable

    return ApiResponse(
        success=True,
        data=OrderStatusResponse(
            status=order.status,
            order_number=order.order_number,
            payment_status=order.payment_status,
            payment_expires_at=order.payment_expires_at,
            multicard_receipt_url=order.multicard_receipt_url,
            table_title=order.table_title,
            hall_title=order.hall_title,
            service_percent=float(order.service_percent),
            alipos_sync_status=order.alipos_sync_status,
        ).model_dump(mode="json"),
    )


@router.post("/{order_id}/switch-to-cash")
async def switch_order_to_cash(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    try:
        order = await switch_customer_order_to_cash(db, current_user, order_id)
    except CustomerOrderNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PaymentSwitchConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PaymentSwitchError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except OrderSubmissionRejected as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=ORDER_SUBMISSION_ERROR_DETAIL,
        ) from exc
    return ApiResponse(
        success=True,
        data=OrderResponse.model_validate(order).model_dump(mode="json"),
    )


@router.post("/{order_id}/retry-payment")
async def retry_order_payment(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    try:
        order = await retry_customer_order_payment(db, current_user, order_id)
    except CustomerOrderNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PaymentRetryConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return ApiResponse(
        success=True,
        data=OrderResponse.model_validate(order).model_dump(mode="json"),
    )
