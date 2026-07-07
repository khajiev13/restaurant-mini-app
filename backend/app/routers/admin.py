from fastapi import APIRouter

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse, UserRoleUpdate
from app.services import admin_user_service

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def search_users(
    current_user: CurrentUserDep,
    db: DbDep,
    query: str = "",
) -> ApiResponse:
    users = await admin_user_service.search_users(db, current_user, query)
    return ApiResponse(
        success=True,
        data=[UserResponse.model_validate(user).model_dump() for user in users],
    )


@router.patch("/users/{telegram_id}/role")
async def update_user_role(
    telegram_id: int,
    body: UserRoleUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    user = await admin_user_service.update_user_role(
        db,
        current_user,
        telegram_id,
        body.role,
    )
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user).model_dump(),
    )
