from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.config import settings
from app.middleware.telegram_auth import DbDep, create_jwt, validate_init_data
from app.models.models import User
from app.schemas.common import ApiResponse
from app.schemas.user import TelegramAuthRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/telegram")
async def telegram_auth(body: TelegramAuthRequest, db: DbDep) -> ApiResponse:
    """Validate Telegram initData, create/update user, return JWT."""
    try:
        user_data = validate_init_data(body.init_data, settings.telegram_bot_token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc

    telegram_id = user_data["id"]

    # Upsert user
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()

    if user:
        user.first_name = user_data.get("first_name", user.first_name)
        user.last_name = user_data.get("last_name")
        user.username = user_data.get("username")
    else:
        user = User(
            telegram_id=telegram_id,
            first_name=user_data.get("first_name", ""),
            last_name=user_data.get("last_name"),
            username=user_data.get("username"),
        )
        db.add(user)

    await db.commit()

    token = create_jwt(telegram_id)
    return ApiResponse(
        success=True,
        data=TokenResponse(access_token=token).model_dump(),
    )
