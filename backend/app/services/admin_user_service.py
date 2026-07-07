from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import User
from app.services.permissions import ROLE_ADMIN, require_admin

VALID_ROLES = {"customer", "staff", "admin"}


async def _lock_user(db: AsyncSession, telegram_id: int) -> User | None:
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id).with_for_update()
    )
    return result.scalar_one_or_none()


async def _lock_admin_users(db: AsyncSession) -> list[User]:
    result = await db.execute(
        select(User)
        .where(User.role == ROLE_ADMIN)
        .order_by(User.telegram_id.asc())
        .with_for_update()
    )
    return list(result.scalars().all())


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

    if role != ROLE_ADMIN:
        # Lock the current admin cohort in a consistent order before deciding whether
        # an admin demotion is allowed. This serializes concurrent demotions so two
        # transactions cannot both observe "more than one admin" and remove them all.
        admins = await _lock_admin_users(db)
        target = next((admin for admin in admins if admin.telegram_id == telegram_id), None)
        if target is None:
            target = await _lock_user(db, telegram_id)
    else:
        target = await _lock_user(db, telegram_id)

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if target.role == ROLE_ADMIN and role != ROLE_ADMIN:
        if len(admins) <= 1:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot remove the final admin role.",
            )

    target.role = role
    await db.commit()
    await db.refresh(target)
    return target
