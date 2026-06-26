"""IdentityResolver 单元测试 — 覆盖整条身份解析管线.

测试维度:
  * 基础校验: 有效 / 无效 / 过期 / 错误类型 / 缺 jti / 用户不存在
  * 安全控制: 黑名单 / 用户禁用 / 租户禁用
  * 缓存语义: 命中跳过 DB / user_token_version 主动失效 / 租户状态缓存
  * 降级: Redis 不可用直查 DB
  * forward-auth: resolve_identity_from_request
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.auth_helpers import resolve_identity_from_request
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.identity import (
    IdentityResolver,
    TokenIdentity,
    invalidate_tenant_status,
    invalidate_user_identity,
)
from app.models.enums import TenantStatus, UserRole


def _payload(*, sub: str | None = None, type_: str = "access", jti: str = "jti-1") -> dict:
    return {"sub": sub or str(uuid.uuid4()), "type": type_, "jti": jti}


def _make_user(
    user_id: str, *, is_active: bool = True, tenant_id: str | None = None, role: UserRole = UserRole.ENGINEER
) -> MagicMock:
    user = MagicMock()
    user.id = uuid.UUID(user_id)
    user.is_active = is_active
    user.tenant_id = uuid.UUID(tenant_id) if tenant_id else None
    user.username = "tester"
    user.role = role
    return user


def _make_tenant(tenant_id: str, status: TenantStatus = TenantStatus.ACTIVE) -> MagicMock:
    tenant = MagicMock()
    tenant.id = uuid.UUID(tenant_id)
    tenant.status = status
    return tenant


class _FakeRedis:
    """内存版 redis.asyncio — get 按 key 取, set/setex/exists/inccr 皆可写."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.store[key] = value

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def incr(self, key: str) -> int:
        self.store[key] = str(int(self.store.get(key, "0")) + 1)
        return int(self.store[key])


@pytest.fixture
def fake_redis() -> _FakeRedis:
    return _FakeRedis()


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock()


def _not_revoked() -> AsyncMock:
    bl = AsyncMock()
    bl.is_revoked = AsyncMock(return_value=False)
    return bl


# ---------------------------------------------------------------------------
# 基础校验
# ---------------------------------------------------------------------------


class TestResolverBasics:
    @patch("app.core.identity.TokenBlacklistService")
    @patch("app.core.identity.decode_token")
    async def test_valid_token_returns_identity(self, mock_decode, mock_bl_cls, mock_db, fake_redis):
        uid = str(uuid.uuid4())
        mock_decode.return_value = _payload(sub=uid)
        mock_bl_cls.return_value = _not_revoked()
        mock_db.get = AsyncMock(return_value=_make_user(uid))

        identity = await IdentityResolver(fake_redis).resolve("tok", mock_db)

        assert isinstance(identity, TokenIdentity)
        assert str(identity.id) == uid
        assert identity.username == "tester"
        assert identity.role == UserRole.ENGINEER

    @patch("app.core.identity.decode_token", side_effect=ValueError("bad"))
    async def test_invalid_token_raises_401(self, _mock, mock_db, fake_redis):
        with pytest.raises(UnauthorizedException):
            await IdentityResolver(fake_redis).resolve("bad", mock_db)

    @patch("app.core.identity.decode_token")
    async def test_wrong_type_raises_401(self, mock_decode, mock_db, fake_redis):
        mock_decode.return_value = _payload(type_="refresh")
        with pytest.raises(UnauthorizedException, match="类型"):
            await IdentityResolver(fake_redis).resolve("t", mock_db)

    @patch("app.core.identity.decode_token")
    async def test_missing_jti_raises_401(self, mock_decode, mock_db, fake_redis):
        mock_decode.return_value = {"sub": str(uuid.uuid4()), "type": "access"}
        with pytest.raises(UnauthorizedException, match="无效"):
            await IdentityResolver(fake_redis).resolve("t", mock_db)

    @patch("app.core.identity.TokenBlacklistService")
    @patch("app.core.identity.decode_token")
    async def test_user_not_found_raises_401(self, mock_decode, mock_bl_cls, mock_db, fake_redis):
        mock_decode.return_value = _payload()
        mock_bl_cls.return_value = _not_revoked()
        mock_db.get = AsyncMock(return_value=None)
        with pytest.raises(UnauthorizedException, match="不存在"):
            await IdentityResolver(fake_redis).resolve("t", mock_db)


# ---------------------------------------------------------------------------
# 安全控制
# ---------------------------------------------------------------------------


class TestResolverSecurity:
    @patch("app.core.identity.TokenBlacklistService")
    @patch("app.core.identity.decode_token")
    async def test_blacklisted_raises_401(self, mock_decode, mock_bl_cls, mock_db, fake_redis):
        mock_decode.return_value = _payload()
        bl = _not_revoked()
        bl.is_revoked = AsyncMock(return_value=True)
        mock_bl_cls.return_value = bl
        with pytest.raises(UnauthorizedException, match="吊销"):
            await IdentityResolver(fake_redis).resolve("t", mock_db)

    @patch("app.core.identity.TokenBlacklistService")
    @patch("app.core.identity.decode_token")
    async def test_inactive_user_raises_403(self, mock_decode, mock_bl_cls, mock_db, fake_redis):
        uid = str(uuid.uuid4())
        mock_decode.return_value = _payload(sub=uid)
        mock_bl_cls.return_value = _not_revoked()
        mock_db.get = AsyncMock(return_value=_make_user(uid, is_active=False))
        with pytest.raises(ForbiddenException, match="禁用"):
            await IdentityResolver(fake_redis).resolve("t", mock_db)

    @patch("app.core.identity.decode_token")
    async def test_disabled_tenant_raises_403(self, mock_decode, mock_db, fake_redis):
        uid, tid = str(uuid.uuid4()), str(uuid.uuid4())
        mock_decode.return_value = _payload(sub=uid)
        # resolve 依次 db.get(User) → db.get(Tenant)
        mock_db.get = AsyncMock(side_effect=[_make_user(uid, tenant_id=tid), _make_tenant(tid, TenantStatus.DISABLED)])
        with pytest.raises(ForbiddenException, match="租户"):
            await IdentityResolver(fake_redis).resolve("t", mock_db)


# ---------------------------------------------------------------------------
# 缓存语义
# ---------------------------------------------------------------------------


class TestResolverCache:
    @patch("app.core.identity.decode_token")
    async def test_cache_hit_skips_user_db(self, mock_decode, mock_db, fake_redis):
        uid = str(uuid.uuid4())
        mock_decode.return_value = _payload(sub=uid)
        mock_db.get = AsyncMock(return_value=_make_user(uid))  # tenant_id=None → 不查 tenant
        resolver = IdentityResolver(fake_redis)

        first = await resolver.resolve("t", mock_db)
        second = await resolver.resolve("t", mock_db)

        assert second.id == first.id
        # 命中缓存: user 仅查一次
        assert mock_db.get.await_count == 1

    @patch("app.core.identity.decode_token")
    async def test_user_version_increment_invalidates(self, mock_decode, mock_db, fake_redis):
        uid = str(uuid.uuid4())
        mock_decode.return_value = _payload(sub=uid)
        mock_db.get = AsyncMock(return_value=_make_user(uid))
        resolver = IdentityResolver(fake_redis)

        await resolver.resolve("t", mock_db)  # miss → 写缓存
        await invalidate_user_identity(fake_redis, uuid.UUID(uid))  # incr user_token_version
        await resolver.resolve("t", mock_db)  # version 变 → miss → 重查

        assert mock_db.get.await_count == 2

    @patch("app.core.identity.decode_token")
    async def test_tenant_status_cached_as_active(self, mock_decode, mock_db, fake_redis):
        uid, tid = str(uuid.uuid4()), str(uuid.uuid4())
        mock_decode.return_value = _payload(sub=uid)
        mock_db.get = AsyncMock(side_effect=[_make_user(uid, tenant_id=tid), _make_tenant(tid, TenantStatus.ACTIVE)])
        await IdentityResolver(fake_redis).resolve("t", mock_db)
        assert fake_redis.store.get(f"tenant_status:{tid}") == "active"

    async def test_invalidate_tenant_status_marks_disabled(self, fake_redis):
        tid = uuid.uuid4()
        await invalidate_tenant_status(fake_redis, tid)
        assert fake_redis.store.get(f"tenant_status:{tid}") == "disabled"


# ---------------------------------------------------------------------------
# 降级
# ---------------------------------------------------------------------------


class TestResolverDegrade:
    @patch("app.core.identity.decode_token")
    async def test_redis_none_falls_back_to_db(self, mock_decode, mock_db):
        uid = str(uuid.uuid4())
        mock_decode.return_value = _payload(sub=uid)
        mock_db.get = AsyncMock(return_value=_make_user(uid))
        identity = await IdentityResolver(None).resolve("t", mock_db)
        assert str(identity.id) == uid


# ---------------------------------------------------------------------------
# forward-auth
# ---------------------------------------------------------------------------


class TestResolveIdentityFromRequest:
    @patch("app.core.identity.decode_token")
    async def test_extracts_identity_from_cookie(self, mock_decode, mock_db, fake_redis):
        uid = str(uuid.uuid4())
        mock_decode.return_value = _payload(sub=uid)
        mock_db.get = AsyncMock(return_value=_make_user(uid))
        request = MagicMock()
        request.cookies = {"kubeai_access_token": "tok"}
        request.headers = {}

        identity = await resolve_identity_from_request(request, mock_db, fake_redis)
        assert str(identity.id) == uid

    async def test_no_token_returns_none(self, mock_db, fake_redis):
        request = MagicMock()
        request.cookies = {}
        request.headers = {}
        assert await resolve_identity_from_request(request, mock_db, fake_redis) is None

    @patch("app.core.identity.decode_token", side_effect=ValueError("bad"))
    async def test_invalid_token_returns_none(self, _mock, mock_db, fake_redis):
        request = MagicMock()
        request.cookies = {"kubeai_access_token": "bad"}
        request.headers = {}
        assert await resolve_identity_from_request(request, mock_db, fake_redis) is None
