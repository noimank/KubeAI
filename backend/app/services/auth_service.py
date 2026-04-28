from datetime import UTC, datetime

import redis.asyncio as aioredis
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.token_blacklist import TokenBlacklistService
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

logger = structlog.get_logger()

LOCKOUT_THRESHOLD = 5
LOCKOUT_SECONDS = 900
ATTEMPTS_TTL = 900


class AuthService:
    def __init__(self, db: AsyncSession, redis: aioredis.Redis):
        self.db = db
        self.redis = redis
        self.blacklist = TokenBlacklistService(redis)

    async def register(self, req: RegisterRequest) -> TokenResponse:
        existing = await self.db.execute(select(User).where(User.username == req.username))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("用户名已存在")

        existing = await self.db.execute(select(User).where(User.email == req.email))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("邮箱已注册")

        user = User(
            username=req.username,
            email=req.email,
            hashed_password=hash_password(req.password),
        )
        self.db.add(user)
        await self.db.flush()

        return self._generate_tokens(str(user.id))

    async def login(self, req: LoginRequest) -> TokenResponse:
        result = await self.db.execute(select(User).where(User.username == req.username))
        user = result.scalar_one_or_none()

        if user is None:
            raise UnauthorizedException("用户名或密码错误")

        await self._check_lockout(str(user.id))

        if not verify_password(req.password, user.hashed_password):
            await self._increment_failed_attempts(str(user.id))
            raise UnauthorizedException("用户名或密码错误")

        await self._reset_failed_attempts(str(user.id))
        return self._generate_tokens(str(user.id))

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        try:
            payload = decode_token(refresh_token)
        except ValueError:
            raise UnauthorizedException("无效或过期的 Refresh Token") from None

        if payload.get("type") != "refresh":
            raise UnauthorizedException("无效的 Token 类型")

        jti = payload.get("jti")
        if not jti:
            raise UnauthorizedException("无效的 Token")

        if await self.blacklist.is_revoked(jti):
            raise UnauthorizedException("Refresh Token 已被吊销")

        exp = payload.get("exp")
        if exp:
            remaining = int(exp - datetime.now(UTC).timestamp())
            if remaining > 0:
                await self.blacklist.revoke_token(jti, remaining)

        user_id = payload.get("sub")
        if not user_id:
            raise UnauthorizedException("无效的 Token")
        return self._generate_tokens(user_id)

    async def logout(self, user_id: str, access_token_jti: str, refresh_token_jti: str | None = None) -> None:
        await self.blacklist.revoke_token(access_token_jti, self._access_token_remaining_ttl())

        if refresh_token_jti:
            await self.blacklist.revoke_token(refresh_token_jti, self._refresh_token_remaining_ttl())

        logger.info("user_logged_out", user_id=user_id)

    def _access_token_remaining_ttl(self) -> int:
        from app.core.config import settings

        return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

    def _refresh_token_remaining_ttl(self) -> int:
        from app.core.config import settings

        return settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400

    async def _check_lockout(self, user_id: str) -> None:
        lock_key = f"login_lock:{user_id}"
        ttl = await self.redis.get(lock_key)
        if ttl is not None:
            remaining = int(ttl)
            minutes = remaining // 60 + (1 if remaining % 60 else 0)
            raise UnauthorizedException(f"账号已锁定, 请 {minutes} 分钟后重试")

    async def _increment_failed_attempts(self, user_id: str) -> None:
        attempts_key = f"login_attempts:{user_id}"
        count = await self.redis.incr(attempts_key)
        if count == 1:
            await self.redis.expire(attempts_key, ATTEMPTS_TTL)

        if count >= LOCKOUT_THRESHOLD:
            lock_key = f"login_lock:{user_id}"
            await self.redis.setex(lock_key, LOCKOUT_SECONDS, str(LOCKOUT_SECONDS))

    async def _reset_failed_attempts(self, user_id: str) -> None:
        attempts_key = f"login_attempts:{user_id}"
        await self.redis.delete(attempts_key)

    def _generate_tokens(self, user_id: str) -> TokenResponse:
        payload = {"sub": user_id}
        return TokenResponse(
            access_token=create_access_token(payload),
            refresh_token=create_refresh_token(payload),
        )
