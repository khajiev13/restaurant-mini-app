import uuid

from fastapi import APIRouter, HTTPException, status

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.schemas.common import ApiResponse
from app.schemas.order import build_staff_order_response
from app.services import staff_delivery_service, staff_table_service

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("/orders/available")
async def available_orders(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    orders = await staff_delivery_service.list_available_orders(db, current_user)
    return ApiResponse(
        success=True,
        data=[
            build_staff_order_response(order).model_dump(mode="json")
            for order in orders
        ],
    )


@router.get("/orders/active")
async def active_order(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    order = await staff_delivery_service.get_active_order(db, current_user)
    return ApiResponse(
        success=True,
        data=build_staff_order_response(order).model_dump(mode="json")
        if order
        else None,
    )


@router.get("/orders/completed")
async def completed_orders(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    orders = await staff_delivery_service.list_completed_orders(db, current_user)
    return ApiResponse(
        success=True,
        data=[
            build_staff_order_response(order).model_dump(mode="json")
            for order in orders
        ],
    )


@router.get("/tables")
async def list_tables(current_user: CurrentUserDep, db: DbDep) -> ApiResponse:
    try:
        result = await staff_table_service.list_staff_tables(db, current_user)
    except staff_table_service.StaffTableDirectoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Table directory is temporarily unavailable",
        ) from exc
    return ApiResponse(success=True, data=result.model_dump(mode="json"))


@router.get("/tables/{table_id}")
async def get_table(
    table_id: uuid.UUID,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    try:
        result = await staff_table_service.get_staff_table(
            db,
            current_user,
            table_id,
        )
    except staff_table_service.StaffTableDirectoryUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Table directory is temporarily unavailable",
        ) from exc
    except staff_table_service.StaffTableNotFound as exc:
        raise HTTPException(status_code=404, detail="Table not found") from exc
    return ApiResponse(success=True, data=result.model_dump(mode="json"))


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
    order = await staff_delivery_service.mark_order_delivered(
        db, current_user, order_id
    )
    return ApiResponse(
        success=True,
        data=build_staff_order_response(order).model_dump(mode="json"),
    )
