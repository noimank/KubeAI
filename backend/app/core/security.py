import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from jose import JWTError, jwt  # type: ignore[import-untyped]

from app.core.config import settings


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def create_access_token(payload: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = payload.copy()
    to_encode["type"] = "access"
    to_encode["jti"] = str(uuid.uuid4())
    expire = datetime.now(UTC) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256"))


def create_refresh_token(payload: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = payload.copy()
    to_encode["type"] = "refresh"
    to_encode["jti"] = str(uuid.uuid4())
    expire = datetime.now(UTC) + (expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode["exp"] = expire
    return str(jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256"))


def decode_token(token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except JWTError as e:
        raise ValueError("无效或过期的 Token") from e
