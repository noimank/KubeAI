import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.casbin import CasbinEnforcer
from app.core.database import async_session_factory
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.identity import IdentityResolver, TokenIdentity
from app.core.redis import get_redis
from app.models.enums import UserRole
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


# ---------------------------------------------------------------------------
# 鉴权依赖 — 全部基于 IdentityResolver (app/core/identity.py), 本文件不再持有任何
# 解码 / 黑名单 / DB 查询逻辑. 错误消息由 resolver 统一产出, 各入口共享.
# ---------------------------------------------------------------------------


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> TokenIdentity:
    """强制鉴权. 解析失败由 resolver 抛 Unauthorized/Forbidden 并冒泡."""
    return await IdentityResolver(redis).resolve(credentials.credentials, db)


async def get_current_user_entity(
    credentials: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> User:
    """同 ``get_current_user`` 但返回完整可变 User ORM.

    鉴权与缓存仍复用 IdentityResolver, 仅在身份解析后补一次 User 查询. 仅供需读写 User
    实体字段的端点 (修改资料 / 改密 / 头像) 使用; 其余端点一律用 ``CurrentUser``
    (TokenIdentity) 以避免无谓的 DB 查询.
    """
    identity = await IdentityResolver(redis).resolve(credentials.credentials, db)
    user = await db.get(User, identity.id)
    if user is None:  # resolver 已校验存在性, 此为防御
        raise UnauthorizedException("用户不存在")
    return user


async def get_optional_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> TokenIdentity | None:
    """可选鉴权 — 无凭证或解析失败均返回 None (不抛)."""
    from fastapi.security.utils import get_authorization_scheme_param

    auth_header = request.headers.get("Authorization", "")
    scheme, param = get_authorization_scheme_param(auth_header)
    if scheme.lower() != "bearer" or not param:
        return None
    try:
        return await IdentityResolver(redis).resolve(param, db)
    except (UnauthorizedException, ForbiddenException):
        return None


CurrentUser = Annotated[TokenIdentity, Depends(get_current_user)]
CurrentUserEntity = Annotated[User, Depends(get_current_user_entity)]
OptionalCurrentUser = Annotated[TokenIdentity | None, Depends(get_optional_current_user)]


async def authenticate_ws_token(
    token: str,
    db: AsyncSession,
    redis: aioredis.Redis | None,
) -> TokenIdentity | None:
    """WebSocket 握手鉴权 — 失败返回 None (WS 无法透传 HTTP 异常, 由调用方关闭连接).

    保留显式 (token, db, redis) 签名以兼容现有 WS 调用点; redis 为 None 时 resolver
    降级为直查 DB.
    """
    try:
        return await IdentityResolver(redis).resolve(token, db)
    except (UnauthorizedException, ForbiddenException):
        return None


async def get_current_user_from_query_or_header(
    request: Request,
    token: str | None = Query(None, alias="token"),
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> TokenIdentity:
    """Authenticate via Bearer header (priority) or ?token= query parameter.

    用于同时支持 API 客户端 (Bearer) 与浏览器直连 (如 <a> 下载 / <img> 的 ?token=)。
    """
    from fastapi.security.utils import get_authorization_scheme_param

    auth_header = request.headers.get("Authorization", "")
    scheme, param = get_authorization_scheme_param(auth_header)
    token_str = param if (scheme.lower() == "bearer" and param) else token
    if not token_str:
        raise UnauthorizedException("未提供认证 Token")
    return await IdentityResolver(redis).resolve(token_str, db)


QueryOrHeaderUser = Annotated[TokenIdentity, Depends(get_current_user_from_query_or_header)]


async def get_current_tenant_id(request: Request) -> str | None:
    return getattr(request.state, "tenant_id", None)


RequireTenant = Annotated[str | None, Depends(get_current_tenant_id)]


def require_permission(resource: str, action: str) -> Any:
    async def _check_permission(current_user: CurrentUser) -> TokenIdentity:
        role = current_user.role.value
        if not CasbinEnforcer.enforce(role, resource, action):
            raise ForbiddenException(f"权限不足: 无法对 {resource} 执行 {action} 操作")
        return current_user

    return _check_permission


def require_tenant_access(resource_tenant_id: uuid.UUID) -> Any:
    async def _check(current_user: CurrentUser) -> TokenIdentity:
        if current_user.role == UserRole.ADMIN:
            return current_user
        if current_user.tenant_id != resource_tenant_id:
            raise ForbiddenException("无权访问其他租户的资源")
        return current_user

    return _check
