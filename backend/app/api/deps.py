import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Any
from urllib.parse import urlparse

import redis.asyncio as aioredis
from fastapi import Depends, Request, WebSocket, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.utils import get_authorization_scheme_param
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth_helpers import COOKIE_NAME
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


async def authenticate_ws(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> TokenIdentity:
    """WebSocket 握手鉴权 — 同源 Cookie, 失败抛 ``WebSocketException`` 拒绝握手.

    浏览器 WebSocket 无法携带 Authorization 头, 使用登录时前端写入的
    ``kubeai_access_token`` Cookie (SameSite=Lax)。相比 ``?token=`` 查询参数,
    JWT 不再泄漏到代理访问日志 / 浏览器历史。Origin 校验防御跨站 WebSocket
    劫持 (CSWSH); 经 nginx ``$host`` 转发的 Host 不含端口, 故仅比较主机名。
    """
    origin = websocket.headers.get("origin")
    if origin:
        origin_host = urlparse(origin).hostname or ""
        request_host = urlparse(f"//{websocket.headers.get('host', '')}").hostname or ""
        if not origin_host or origin_host != request_host:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="跨站 WebSocket 连接被拒绝")

    token = websocket.cookies.get(COOKIE_NAME)
    if not token:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="未认证")
    try:
        identity = await IdentityResolver(redis).resolve(token, db)
    except (UnauthorizedException, ForbiddenException) as exc:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="认证失败") from exc
    if identity.tenant_id is None:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="用户未归属租户")
    return identity


WsUser = Annotated[TokenIdentity, Depends(authenticate_ws)]


async def get_current_user_from_header_or_cookie(
    request: Request,
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> TokenIdentity:
    """Authenticate via Bearer header (priority) or same-origin Cookie.

    用于浏览器原生请求 (<img>/<video>/<a> 下载等无法携带 Authorization 头的场景):
    同源请求自动携带 ``kubeai_access_token`` Cookie, JWT 不再经 URL 传输。
    Cookie 通道要求 ``Sec-Fetch-Site`` 非 cross-site, 阻断跨站页面借会话 Cookie 鉴权
    (与 Cookie 的 SameSite=Lax 互为纵深防御; Bearer 头为显式凭证, 不受此限)。
    """
    auth_header = request.headers.get("Authorization", "")
    scheme, param = get_authorization_scheme_param(auth_header)
    if scheme.lower() == "bearer" and param:
        return await IdentityResolver(redis).resolve(param, db)

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise UnauthorizedException("未提供认证 Token")
    if request.headers.get("sec-fetch-site", "").lower() == "cross-site":
        raise UnauthorizedException("跨站请求被拒绝")
    return await IdentityResolver(redis).resolve(token, db)


HeaderOrCookieUser = Annotated[TokenIdentity, Depends(get_current_user_from_header_or_cookie)]


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
