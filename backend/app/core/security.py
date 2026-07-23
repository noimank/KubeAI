import asyncio
import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt  # type: ignore[import-untyped]

from app.core.config import settings


async def hash_password(plain: str) -> str:
    hashed = await asyncio.to_thread(bcrypt.hashpw, plain.encode(), bcrypt.gensalt())
    return hashed.decode()


async def verify_password(plain: str, hashed: str) -> bool:
    return await asyncio.to_thread(bcrypt.checkpw, plain.encode(), hashed.encode())


def generate_api_token(prefix: str = "sk") -> str:
    raw = secrets.token_hex(32)
    return f"{prefix}-{raw}"


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_api_token(token: str, token_hash: str) -> bool:
    return hash_api_token(token) == token_hash


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


# ── Fernet 对称加密（数据库连接密码等敏感字段） ──

_fernet: Fernet | None = None


def _derive_fernet_key(secret_key: str) -> bytes:
    """从 SECRET_KEY 派生 32 字节 Fernet 密钥（SHA256 → base64url）。"""
    digest = hashlib.sha256(secret_key.encode()).digest()
    return base64.urlsafe_b64encode(digest)


def get_fernet() -> Fernet:
    """惰性获取全局 Fernet 实例。"""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_derive_fernet_key(settings.SECRET_KEY))
    return _fernet


def encrypt_password(plain: str) -> str:
    """加密明文密码。"""
    return get_fernet().encrypt(plain.encode()).decode()


def decrypt_password(cipher: str) -> str:
    """解密密文密码。"""
    return get_fernet().decrypt(cipher.encode()).decode()
