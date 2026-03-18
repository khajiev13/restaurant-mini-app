import hashlib
import hmac
import json
import time
from typing import Annotated
from urllib.parse import parse_qs, unquote

from fastapi import Depends, Header, HTTPException, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.models import User


def validate_init_data(init_data: str, bot_token: str) -> dict:
    """Validate Telegram initData using HMAC-SHA256.

    Returns the parsed data dict if valid, raises ValueError otherwise.
    See: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    parsed = parse_qs(init_data)

    # Extract hash
    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        raise ValueError("Missing hash in initData")

    # Check auth_date is not too old (allow 1 hour)
    auth_date_str = parsed.get("auth_date", [None])[0]
    if not auth_date_str:
        raise ValueError("Missing auth_date in initData")

    auth_date = int(auth_date_str)
    if time.time() - auth_date > 3600:
        raise ValueError("initData is too old")

    # Build data-check-string: sorted key=value pairs, excluding hash
    data_pairs = []
    for key, values in parsed.items():
        if key == "hash":
            continue
        data_pairs.append(f"{key}={values[0]}")
    data_pairs.sort()
    data_check_string = "\n".join(data_pairs)

    # Calculate HMAC
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    # Constant-time comparison
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid initData hash")

    # Parse user data
    user_data_raw = parsed.get("user", [None])[0]
    if not user_data_raw:
        raise ValueError("Missing user in initData")

    return json.loads(unquote(user_data_raw))


def create_jwt(telegram_id: int) -> str:
    """Create a JWT token for a Telegram user."""
    payload = {
        "sub": str(telegram_id),
        "exp": int(time.time()) + settings.jwt_expire_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_jwt(token: str) -> int:
    """Decode JWT and return the Telegram user ID."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        telegram_id = int(payload["sub"])
        return telegram_id
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> User:
    """Extract and validate JWT from Authorization header, return User."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
        )
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )
    token = authorization[7:]
    telegram_id = decode_jwt(token)

    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]
DbDep = Annotated[AsyncSession, Depends(get_db)]
