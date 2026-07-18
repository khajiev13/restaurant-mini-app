import uuid

from fastapi import APIRouter

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.schemas.common import ApiResponse
from app.schemas.order import build_staff_order_response
from app.services import staff_delivery_service

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/orders/available")
async def available_orders(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    orders = await staff_delivery_service.list_available_orders(db, current_user)
    return ApiResponse(
        success=True,
        data=[build_staff_order_response(order).model_dump(mode="json") for order in orders],
    )


@router.get("/orders/active")
async def active_order(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    order = await staff_delivery_service.get_active_order(db, current_user)
    return ApiResponse(
        success=True,
        data=build_staff_order_response(order).model_dump(mode="json") if order else None,
    )


@router.get("/orders/completed")
async def completed_orders(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    orders = await staff_delivery_service.list_completed_orders(db, current_user)
    return ApiResponse(
        success=True,
        data=[build_staff_order_response(order).model_dump(mode="json") for order in orders],
    )


@router.get("/orders/{order_id}")
async def get_staff_order(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    order = await staff_delivery_service.get_staff_order(db, current_user, order_id)
    return ApiResponse(
        success=True,
        data=build_staff_order_response(order).model_dump(mode="json"),
    )


@router.post("/orders/{order_id}/take")
async def take_order(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    order = await staff_delivery_service.take_order(db, current_user, order_id)
    return ApiResponse(
        success=True,
        data=build_staff_order_response(order).model_dump(mode="json"),
    )


@router.post("/orders/{order_id}/delivered")
async def mark_delivered(
    order_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    order = await staff_delivery_service.mark_order_delivered(db, current_user, order_id)
    return ApiResponse(
        success=True,
        data=build_staff_order_response(order).model_dump(mode="json"),
    )
