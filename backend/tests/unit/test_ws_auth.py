"""authenticate_ws 单元测试 — WebSocket 握手鉴权管线.

覆盖维度:
  * Origin 校验 (CSWSH 防御): 跨站拒绝 / 同源放行(含端口差异) / 非浏览器客户端无 Origin 放行
  * Cookie 鉴权: 无 Cookie 拒绝 / 无效 token 拒绝
  * 身份约束: 无租户身份拒绝 / 合法身份放行
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketException

from app.api.deps import authenticate_ws
from app.core.auth_helpers import COOKIE_NAME
from app.core.exceptions import UnauthorizedException
from app.core.identity import TokenIdentity
from app.models.enums import UserRole


class _FakeWebSocket:
    """仅实现 authenticate_ws 依赖的 headers / cookies 接口."""

    def __init__(self, *, headers: dict[str, str] | None = None, cookies: dict[str, str] | None = None):
        self.headers = headers or {}
        self.cookies = cookies or {}


def _identity(*, tenant_id: uuid.UUID | None) -> TokenIdentity:
    return TokenIdentity(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username="tester",
        role=UserRole.ENGINEER,
        jti="jti-1",
    )


async def _call(ws: _FakeWebSocket) -> TokenIdentity:
    with patch("app.api.deps.IdentityResolver") as resolver_cls:
        resolver = resolver_cls.return_value
        resolver.resolve = AsyncMock(return_value=_identity(tenant_id=uuid.uuid4()))
        return await authenticate_ws(ws, db=AsyncMock(), redis=MagicMock())


async def test_cross_site_origin_rejected():
    ws = _FakeWebSocket(
        headers={"origin": "http://evil.example.com", "host": "kubeai.example.com"},
        cookies={COOKIE_NAME: "token"},
    )
    with pytest.raises(WebSocketException, match="跨站"):
        await _call(ws)


async def test_same_origin_with_port_mismatch_allowed():
    # nginx $host 转发不含端口, Origin 带端口 — 仅比较主机名须放行
    ws = _FakeWebSocket(
        headers={"origin": "http://kubeai.example.com:30080", "host": "kubeai.example.com"},
        cookies={COOKIE_NAME: "token"},
    )
    identity = await _call(ws)
    assert identity.tenant_id is not None


async def test_missing_origin_allowed():
    # 非浏览器客户端 (curl / 测试) 不带 Origin
    ws = _FakeWebSocket(cookies={COOKIE_NAME: "token"})
    identity = await _call(ws)
    assert identity.tenant_id is not None


async def test_missing_cookie_rejected():
    ws = _FakeWebSocket(headers={"origin": "http://kubeai.example.com", "host": "kubeai.example.com"})
    with pytest.raises(WebSocketException, match="未认证"):
        await _call(ws)


async def test_invalid_token_rejected():
    ws = _FakeWebSocket(
        headers={"origin": "http://kubeai.example.com", "host": "kubeai.example.com"},
        cookies={COOKIE_NAME: "bad-token"},
    )
    with patch("app.api.deps.IdentityResolver") as resolver_cls:
        resolver = resolver_cls.return_value
        resolver.resolve = AsyncMock(side_effect=UnauthorizedException("token 无效"))
        with pytest.raises(WebSocketException, match="认证失败"):
            await authenticate_ws(ws, db=AsyncMock(), redis=MagicMock())


async def test_tenantless_identity_rejected():
    ws = _FakeWebSocket(
        headers={"origin": "http://kubeai.example.com", "host": "kubeai.example.com"},
        cookies={COOKIE_NAME: "token"},
    )
    with patch("app.api.deps.IdentityResolver") as resolver_cls:
        resolver = resolver_cls.return_value
        resolver.resolve = AsyncMock(return_value=_identity(tenant_id=None))
        with pytest.raises(WebSocketException, match="租户"):
            await authenticate_ws(ws, db=AsyncMock(), redis=MagicMock())


async def test_valid_identity_returns():
    ws = _FakeWebSocket(
        headers={"origin": "https://kubeai.example.com", "host": "kubeai.example.com"},
        cookies={COOKIE_NAME: "token"},
    )
    identity = await _call(ws)
    assert identity.role == UserRole.ENGINEER
