"""get_current_user_from_header_or_cookie 单元测试 — 浏览器原生请求鉴权管线.

覆盖维度:
  * Bearer 通道: API 客户端直接放行 (显式凭证, 不受 Sec-Fetch-Site 约束)
  * Cookie 通道: 同源放行 / 无 Sec-Fetch-Site (非浏览器) 放行 / cross-site 拒绝
  * 无凭证拒绝 / 无效 token 上抛 Unauthorized
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.deps import get_current_user_from_header_or_cookie
from app.core.auth_helpers import COOKIE_NAME
from app.core.exceptions import UnauthorizedException
from app.core.identity import TokenIdentity
from app.models.enums import UserRole


class _FakeRequest:
    """仅实现依赖所需的 headers / cookies 接口."""

    def __init__(self, *, headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def _identity() -> TokenIdentity:
    return TokenIdentity(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        username="tester",
        role=UserRole.ENGINEER,
        jti="jti-1",
    )


async def _call(request: _FakeRequest) -> TokenIdentity:
    with patch("app.api.deps.IdentityResolver") as resolver_cls:
        resolver = resolver_cls.return_value
        resolver.resolve = AsyncMock(return_value=_identity())
        return await get_current_user_from_header_or_cookie(request, db=AsyncMock(), redis=MagicMock())


async def test_bearer_header_authenticates():
    identity = await _call(_FakeRequest(headers={"Authorization": "Bearer abc"}))
    assert identity.role == UserRole.ENGINEER


async def test_bearer_ignores_cross_site():
    # Bearer 是显式凭证, 即使来自跨站页面也非 CSRF 范畴 (页面拿不到 token 本身)
    identity = await _call(_FakeRequest(headers={"Authorization": "Bearer abc", "sec-fetch-site": "cross-site"}))
    assert identity.role == UserRole.ENGINEER


async def test_cookie_same_origin_authenticates():
    identity = await _call(_FakeRequest(headers={"sec-fetch-site": "same-origin"}, cookies={COOKIE_NAME: "token"}))
    assert identity.role == UserRole.ENGINEER


async def test_cookie_without_sec_fetch_site_authenticates():
    # 非浏览器客户端 (curl / 测试) 不发送 Sec-Fetch-Site
    identity = await _call(_FakeRequest(cookies={COOKIE_NAME: "token"}))
    assert identity.role == UserRole.ENGINEER


async def test_cookie_cross_site_rejected():
    with pytest.raises(UnauthorizedException, match="跨站"):
        await _call(_FakeRequest(headers={"sec-fetch-site": "cross-site"}, cookies={COOKIE_NAME: "token"}))


async def test_no_credentials_rejected():
    with pytest.raises(UnauthorizedException, match="未提供"):
        await _call(_FakeRequest())


async def test_invalid_cookie_token_raises():
    with patch("app.api.deps.IdentityResolver") as resolver_cls:
        resolver = resolver_cls.return_value
        resolver.resolve = AsyncMock(side_effect=UnauthorizedException("token 无效"))
        with pytest.raises(UnauthorizedException, match="token 无效"):
            await get_current_user_from_header_or_cookie(
                _FakeRequest(cookies={COOKIE_NAME: "bad"}), db=AsyncMock(), redis=MagicMock()
            )
