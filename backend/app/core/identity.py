"""统一身份解析层 — 所有鉴权入口的单一来源.

历史问题: 鉴权逻辑散落在 ``deps.py`` 的四个函数 + ``auth_helpers.validate_token_and_get_user``,
校验维度参差不齐 — 黑名单 / 租户状态有的入口查、有的不查, 且 ``validate_token_and_get_user``
根本不查黑名单 (forward-auth 登出后 token 在 180min 有效期内仍可用). 本模块将整条管线收敛为
一处, 所有入口 (FastAPI 依赖 / WebSocket 握手 / APISIX forward-auth) 共享同一套校验与缓存.

分层原则 (鉴权架构的核心约定)
-------------------------------
    身份解析层 (本模块)  — 管「你是谁」. 身份在会话期内稳定, 故可缓存、可主动失效.
    端点层               — 管「你能否访问这个资源」(job 归属 / 终态 / RBAC).
                          资源状态随时变化, 绝不缓存.

解析管线
--------
    token → decode(过期即时) → 黑名单(登出即时) → 身份缓存(命中即返回)
         → miss: 查 user(is_active) → 租户状态(启用) → 构造 TokenIdentity → 回填缓存

失效语义 (每一类变更都即时或近即时生效)
-----------------------------------------
    token 过期        decode 每次, 即时
    登出 / 单 token 吊销   黑名单每次查, 即时 (auth_service.logout 已接入)
    用户禁用 / 删除    ``user_token_version`` incr → cache key 改变 → 下次必 miss
                      (接入点: users.toggle_user_status / delete_user)
    租户禁用           ``tenant_status`` 主动覆盖为 disabled → 即时
                      (接入点: tenants.toggle_tenant_status)

降级: Redis 不可用时 (``redis is None``, 如某些 WebSocket 调用路径) 跳过黑名单与缓存,
直查 DB, 不阻塞鉴权.

返回约定
--------
``resolve`` 失败时抛 ``UnauthorizedException`` / ``ForbiddenException`` (带细分原因),
成功返回 ``TokenIdentity``. 强制鉴权依赖 (``get_current_user``) 直接透传异常;
可选 / WS / forward-auth 入口用 ``try/except`` 转为 ``None``. 这样细分错误消息全局统一,
而非各入口各写一套.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.core.config import settings
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_token
from app.core.token_blacklist import TokenBlacklistService
from app.models.enums import TenantStatus, UserRole

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.user import User

# 本模块属核心安全路径, 关键决策均落日志
logger = structlog.get_logger(__name__)


IDENTITY_CACHE_PREFIX = "identity"
TENANT_STATUS_PREFIX = "tenant_status"
USER_TOKEN_VERSION_PREFIX = "user_token_version"  # 与 token_blacklist.py 保持一致


# ---------------------------------------------------------------------------
# TokenIdentity — 解析后的可信身份 (替代散落各处的 User ORM 作鉴权载体)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TokenIdentity:
    """从 access token 解析出的可信身份.

    仅含「鉴权决策」所需字段 (id / 租户 / 角色 / 用户名 / jti). 需要完整可变 User 实体
    (如修改个人资料、改密) 的端点应走 ``get_current_user_entity`` 另查 DB, 而非依赖此对象.
    """

    id: uuid.UUID
    tenant_id: uuid.UUID | None
    username: str
    role: UserRole
    jti: str

    @classmethod
    def from_user(cls, user: User, jti: str) -> TokenIdentity:
        return cls(
            id=user.id,
            tenant_id=user.tenant_id,
            username=user.username,
            role=user.role,
            jti=jti,
        )

    def to_cache(self) -> str:
        return json.dumps(
            {
                "id": str(self.id),
                "tenant_id": str(self.tenant_id) if self.tenant_id else None,
                "username": self.username,
                "role": self.role.value,
                "jti": self.jti,
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_cache(cls, raw: str) -> TokenIdentity:
        data = json.loads(raw)
        return cls(
            id=uuid.UUID(data["id"]),
            tenant_id=uuid.UUID(data["tenant_id"]) if data["tenant_id"] else None,
            username=data["username"],
            role=UserRole(data["role"]),
            jti=data["jti"],
        )


# ---------------------------------------------------------------------------
# IdentityResolver — 无状态, 每次请求构造 (持有本次可用的 redis)
# ---------------------------------------------------------------------------


class IdentityResolver:
    """解析 access token 到 ``TokenIdentity``.

    构造时传入本次请求可用的 Redis 连接 (``None`` 表示降级: 跳过黑名单与缓存, 直查 DB).
    """

    def __init__(self, redis: aioredis.Redis | None = None) -> None:
        self.redis = redis

    async def resolve(self, token: str, db: AsyncSession) -> TokenIdentity:
        """解析 token, 失败抛 ``UnauthorizedException`` / ``ForbiddenException``."""
        # 1. 解码 + 基本字段 (过期 / 签名错误 / 类型不符 → 401)
        try:
            payload = decode_token(token)
        except ValueError as e:
            raise UnauthorizedException("无效或过期的 Token") from e

        if payload.get("type") != "access":
            raise UnauthorizedException("无效的 Token 类型")

        jti = payload.get("jti")
        sub = payload.get("sub")
        if not jti or not sub:
            raise UnauthorizedException("无效的 Token")

        try:
            user_id = uuid.UUID(sub)
        except (ValueError, TypeError) as e:
            raise UnauthorizedException("无效的 Token") from e

        # 2. 黑名单 — 登出 / 单 token 吊销即时生效
        if self.redis is not None and await TokenBlacklistService(self.redis).is_revoked(jti):
            raise UnauthorizedException("Token 已被吊销")

        # 3. 身份缓存 (user_token_version 维度, 用户禁用 / 删除时 incr 即失效)
        identity = await self._load_cached(user_id)
        if identity is None:
            identity = await self._resolve_from_db(user_id, jti, db)
            await self._store_cached(user_id, identity)

        # 4. 租户状态 — 启用检查 (短 TTL 缓存 + 禁用时主动覆盖)
        if identity.tenant_id is not None and not await self._is_tenant_active(identity.tenant_id, db):
            raise ForbiddenException("租户已被禁用, 请联系管理员")

        return identity

    # -- 身份缓存 ----------------------------------------------------------

    async def _load_cached(self, user_id: uuid.UUID) -> TokenIdentity | None:
        if self.redis is None:
            return None
        version = await self._user_token_version(user_id)
        key = f"{IDENTITY_CACHE_PREFIX}:{user_id}:{version}"
        raw = await self.redis.get(key)
        if not raw:
            return None
        try:
            return TokenIdentity.from_cache(raw)
        except (ValueError, KeyError, TypeError):
            logger.warning("identity_cache_corrupt", key=key)
            return None

    async def _store_cached(self, user_id: uuid.UUID, identity: TokenIdentity) -> None:
        if self.redis is None:
            return
        version = await self._user_token_version(user_id)
        key = f"{IDENTITY_CACHE_PREFIX}:{user_id}:{version}"
        await self.redis.setex(key, settings.IDENTITY_CACHE_TTL_SECONDS, identity.to_cache())

    async def _user_token_version(self, user_id: uuid.UUID) -> str:
        """``user_token_version:<user_id>`` — 缺省 "0". 禁用 / 删除用户时 incr 即让其自增."""
        assert self.redis is not None
        version = await self.redis.get(f"{USER_TOKEN_VERSION_PREFIX}:{user_id}")
        return version or "0"

    # -- DB 解析 (缓存 miss) -----------------------------------------------

    async def _resolve_from_db(self, user_id: uuid.UUID, jti: str, db: AsyncSession) -> TokenIdentity:
        from app.models.user import User

        user = await db.get(User, user_id)
        if user is None:
            raise UnauthorizedException("用户不存在")
        if not user.is_active:
            raise ForbiddenException("用户已被禁用")
        return TokenIdentity.from_user(user, jti)

    # -- 租户状态 -----------------------------------------------------------

    async def _is_tenant_active(self, tenant_id: uuid.UUID, db: AsyncSession) -> bool:
        if self.redis is not None:
            key = f"{TENANT_STATUS_PREFIX}:{tenant_id}"
            cached = await self.redis.get(key)
            if cached == "active":
                return True
            if cached == "disabled":
                return False

        from app.models.tenant import Tenant

        tenant = await db.get(Tenant, tenant_id)
        active = tenant is not None and tenant.status == TenantStatus.ACTIVE

        if self.redis is not None:
            await self.redis.setex(
                f"{TENANT_STATUS_PREFIX}:{tenant_id}",
                settings.TENANT_STATUS_CACHE_TTL_SECONDS,
                "active" if active else "disabled",
            )
        return active


# ---------------------------------------------------------------------------
# 主动失效 — 供管理操作 (禁用用户 / 禁用租户) 调用
# ---------------------------------------------------------------------------


async def invalidate_user_identity(redis: aioredis.Redis, user_id: uuid.UUID) -> None:
    """使某用户的所有已缓存身份立即失效.

    通过 ``incr user_token_version:<user_id>`` 改变 cache key 维度,
    该用户所有副本上的身份缓存下次请求必然 miss → 重查 DB → 命中禁用状态.
    对称于 ``TokenBlacklistService.revoke_all_user_tokens``, 统一从此处入口.
    """
    await TokenBlacklistService(redis).revoke_all_user_tokens(str(user_id))


async def invalidate_tenant_status(redis: aioredis.Redis, tenant_id: uuid.UUID) -> None:
    """使某租户的状态缓存立即反映「已禁用」, 该租户用户的身份解析随即被拒."""
    await redis.set(
        f"{TENANT_STATUS_PREFIX}:{tenant_id}",
        "disabled",
        ex=settings.TENANT_STATUS_CACHE_TTL_SECONDS,
    )
