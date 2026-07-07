from fastapi import HTTPException, status

from app.models.models import User

ROLE_CUSTOMER = "customer"
ROLE_STAFF = "staff"
ROLE_ADMIN = "admin"
STAFF_ROLES = {ROLE_STAFF, ROLE_ADMIN}


def require_role(user: User, allowed_roles: set[str]) -> None:
    if user.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )


def is_staff_role(user: User) -> bool:
    return user.role in STAFF_ROLES
