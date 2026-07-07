from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.services.permissions import ROLE_ADMIN, require_admin

VALID_ROLES = {"customer", "staff", "admin"}


async def search_users(db: AsyncSession, current_user: User, query: str) -> list[User]:
    require_admin(current_user)

    normalized_query = query.strip()
    statement = select(User).order_by(User.created_at.desc()).limit(25)
    if normalized_query:
        pattern = f"%{normalized_query}%"
        statement = statement.where(
            or_(
                User.first_name.ilike(pattern),
                User.last_name.ilike(pattern),
                User.username.ilike(pattern),
                User.phone_number.ilike(pattern),
            )
        )

    result = await db.execute(statement)
    return list(result.scalars().all())


async def update_user_role(
    db: AsyncSession,
    current_user: User,
    telegram_id: int,
    role: str,
) -> User:
    require_admin(current_user)
    if role not in VALID_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid role",
        )

    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id).with_for_update()
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if target.role == ROLE_ADMIN and role != ROLE_ADMIN:
        admin_count_result = await db.execute(
            select(func.count()).select_from(User).where(User.role == ROLE_ADMIN)
        )
        admin_count = int(admin_count_result.scalar() or 0)
        if admin_count <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the final admin role.",
            )

    target.role = role
    await db.commit()
    await db.refresh(target)
    return target
