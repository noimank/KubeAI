from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import ConflictException, ForbiddenException, UnauthorizedException
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.token_blacklist import TokenBlacklistService
from app.models.enums import AuditAction, ResourceType
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

LOCKOUT_THRESHOLD = 5
LOCKOUT_SECONDS = 900
ATTEMPTS_TTL = 900


class AuthService:
    def __init__(self, db: AsyncSession, redis: aioredis.Redis):
        self.db = db
        self.redis = redis
        self.blacklist = TokenBlacklistService(redis)

    async def register(self, req: RegisterRequest, audit_context: dict[str, Any] | None = None) -> TokenResponse:
        if not settings.ALLOW_USER_REGISTRATION:
            raise ForbiddenException("当前不允许用户自行注册")

        existing = await self.db.execute(select(User).where(User.username == req.username))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("用户名已存在")

        existing = await self.db.execute(select(User).where(User.email == req.email))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("邮箱已注册")

        user = User(
            username=req.username,
            email=req.email,
            hashed_password=await hash_password(req.password),
        )
        self.db.add(user)
        await self.db.flush()

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.REGISTER,
                resource_type=ResourceType.USER,
                resource_id=str(user.id),
                detail={"username": user.username, "email": user.email},
                user_id=user.id,
                **audit_context,
            )

        return self._generate_tokens(str(user.id), str(user.tenant_id) if user.tenant_id else None)

    async def login(self, req: LoginRequest, audit_context: dict[str, Any] | None = None) -> TokenResponse:
        result = await self.db.execute(select(User).where(User.username == req.username))
        user = result.scalar_one_or_none()

        if user is None:
            if audit_context:
                audit_svc = AuditService(self.db)
                await audit_svc.log_action(
                    action=AuditAction.LOGIN,
                    resource_type=ResourceType.USER,
                    detail={"success": False, "reason": "user_not_found", "username": req.username},
                    **audit_context,
                )
            raise UnauthorizedException("用户名或密码错误")

        if not user.is_active:
            raise ForbiddenException("用户已被禁用")

        await self._check_lockout(str(user.id))

        if not await verify_password(req.password, user.hashed_password):
            if audit_context:
                audit_svc = AuditService(self.db)
                await audit_svc.log_action(
                    action=AuditAction.LOGIN,
                    resource_type=ResourceType.USER,
                    resource_id=str(user.id),
                    detail={"success": False, "reason": "invalid_credentials"},
                    user_id=user.id,
                    **audit_context,
                )
            await self._increment_failed_attempts(str(user.id))
            raise UnauthorizedException("用户名或密码错误")

        await self._reset_failed_attempts(str(user.id))

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.LOGIN,
                resource_type=ResourceType.USER,
                resource_id=str(user.id),
                detail={"success": True},
                user_id=user.id,
                **audit_context,
            )

        return self._generate_tokens(str(user.id), str(user.tenant_id) if user.tenant_id else None)

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

        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise UnauthorizedException("用户不存在")
        if not user.is_active:
            raise UnauthorizedException("用户已被禁用")

        return self._generate_tokens(str(user.id), str(user.tenant_id) if user.tenant_id else None)

    async def logout(
        self,
        user_id: str,
        access_token_jti: str,
        refresh_token_jti: str | None = None,
        access_exp: float | None = None,
        refresh_exp: float | None = None,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        from app.core.config import settings

        access_ttl = self._calc_remaining_ttl(access_exp, settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        await self.blacklist.revoke_token(access_token_jti, access_ttl)

        if refresh_token_jti:
            refresh_ttl = self._calc_remaining_ttl(refresh_exp, settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
            await self.blacklist.revoke_token(refresh_token_jti, refresh_ttl)

        if audit_context:
            audit_svc = AuditService(self.db)
            await audit_svc.log_action(
                action=AuditAction.LOGOUT,
                resource_type=ResourceType.USER,
                resource_id=user_id,
                user_id=uuid.UUID(user_id) if user_id else None,
                **audit_context,
            )

        logger.info("user_logged_out", user_id=user_id)

    def _calc_remaining_ttl(self, exp: float | None, default_seconds: int) -> int:
        if exp:
            remaining = int(exp - datetime.now(UTC).timestamp())
            return max(remaining, 0)
        return default_seconds

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

    def _generate_tokens(self, user_id: str, tenant_id: str | None = None) -> TokenResponse:
        payload = {"sub": user_id}
        if tenant_id is not None:
            payload["tenant_id"] = tenant_id
        return TokenResponse(
            access_token=create_access_token(payload),
            refresh_token=create_refresh_token(payload),
            tenant_id=tenant_id,
        )
