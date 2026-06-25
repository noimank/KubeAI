import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.casbin import CasbinEnforcer
from app.core.database import async_session_factory
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.redis import get_redis
from app.core.security import decode_token
from app.core.token_blacklist import TokenBlacklistService
from app.models.enums import TenantStatus, UserRole
from app.models.user import User

security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> User:
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise UnauthorizedException("无效或过期的 Token") from None

    if payload.get("type") != "access":
        raise UnauthorizedException("无效的 Token 类型")

    jti = payload.get("jti")
    if not jti:
        raise UnauthorizedException("无效的 Token")

    blacklist = TokenBlacklistService(redis)
    if await blacklist.is_revoked(jti):
        raise UnauthorizedException("Token 已被吊销")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("无效的 Token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("用户不存在")
    if not user.is_active:
        raise ForbiddenException("用户已被禁用")

    if user.tenant_id is not None:
        from app.models.tenant import Tenant

        tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if tenant and tenant.status == TenantStatus.DISABLED:
            raise ForbiddenException("租户已被禁用, 请联系管理员")

    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> User | None:
    try:
        from fastapi.security.utils import get_authorization_scheme_param

        auth_header = request.headers.get("Authorization", "")
        scheme, param = get_authorization_scheme_param(auth_header)
        if scheme.lower() != "bearer" or not param:
            return None
        credentials = HTTPAuthorizationCredentials(scheme=scheme, credentials=param)
    except Exception:
        return None

    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            return None
        jti = payload.get("jti")
        if not jti:
            return None
        blacklist = TokenBlacklistService(redis)
        if await blacklist.is_revoked(jti):
            return None
        user_id = payload.get("sub")
        if not user_id:
            return None
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            return None
        return user
    except Exception:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalCurrentUser = Annotated[User | None, Depends(get_optional_current_user)]


async def authenticate_ws_token(
    token: str,
    db: AsyncSession,
    redis: aioredis.Redis | None,
) -> User | None:
    """Validate a WebSocket access token.

    Returns the User on success, None on any failure. Does not raise — WebSocket
    handshakes cannot surface HTTP exceptions, so callers close the socket
    themselves when this returns None. Used by /ws and the per-job log stream.
    """
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    if payload.get("type") != "access":
        return None
    jti = payload.get("jti")
    if not jti:
        return None
    if redis is not None and await TokenBlacklistService(redis).is_revoked(jti):
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def get_current_user_from_query_or_header(
    request: Request,
    token: str | None = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> User:
    """Authenticate via Bearer header (priority) or ?token= query parameter.

    Used by endpoints that may be accessed both via API client (Bearer header)
    and direct browser requests like <img> tags (query parameter).
    """
    from fastapi.security.utils import get_authorization_scheme_param

    auth_header = request.headers.get("Authorization", "")
    scheme, param = get_authorization_scheme_param(auth_header)

    # Prefer Bearer header, fall back to query parameter
    token_str = param if (scheme.lower() == "bearer" and param) else token

    if not token_str:
        raise UnauthorizedException("未提供认证 Token")

    try:
        payload = decode_token(token_str)
    except ValueError:
        raise UnauthorizedException("无效或过期的 Token") from None

    if payload.get("type") != "access":
        raise UnauthorizedException("无效的 Token 类型")

    jti = payload.get("jti")
    if not jti:
        raise UnauthorizedException("无效的 Token")

    blacklist = TokenBlacklistService(redis)
    if await blacklist.is_revoked(jti):
        raise UnauthorizedException("Token 已被吊销")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("无效的 Token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("用户不存在")
    if not user.is_active:
        raise ForbiddenException("用户已被禁用")

    if user.tenant_id is not None:
        from app.models.tenant import Tenant

        tenant_result = await db.execute(select(Tenant).where(Tenant.id == user.tenant_id))
        tenant = tenant_result.scalar_one_or_none()
        if tenant and tenant.status == TenantStatus.DISABLED:
            raise ForbiddenException("租户已被禁用, 请联系管理员")

    return user


QueryOrHeaderUser = Annotated[User, Depends(get_current_user_from_query_or_header)]


async def get_current_tenant_id(request: Request) -> str | None:
    return getattr(request.state, "tenant_id", None)


RequireTenant = Annotated[str | None, Depends(get_current_tenant_id)]


def require_permission(resource: str, action: str) -> Any:
    async def _check_permission(current_user: CurrentUser) -> User:
        role = current_user.role.value
        if not CasbinEnforcer.enforce(role, resource, action):
            raise ForbiddenException(f"权限不足: 无法对 {resource} 执行 {action} 操作")
        return current_user

    return _check_permission


def require_tenant_access(resource_tenant_id: uuid.UUID) -> Any:
    async def _check(current_user: CurrentUser) -> User:
        if current_user.role == UserRole.ADMIN:
            return current_user
        if current_user.tenant_id != resource_tenant_id:
            raise ForbiddenException("无权访问其他租户的资源")
        return current_user

    return _check
