from fastapi import APIRouter

from app.middleware.telegram_auth import CurrentUserDep, DbDep
from app.schemas.common import ApiResponse
from app.schemas.user import UserResponse, UserUpdate

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_me(current_user: CurrentUserDep) -> ApiResponse:
    """Get current user's profile."""
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(current_user).model_dump(),
    )


@router.put("/me")
async def update_me(
    body: UserUpdate,
    current_user: CurrentUserDep,
    db: DbDep,
) -> ApiResponse:
    """Update current user's profile."""
    if body.phone_number is not None:
        current_user.phone_number = body.phone_number
    await db.commit()
    await db.refresh(current_user)
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(current_user).model_dump(),
    )
