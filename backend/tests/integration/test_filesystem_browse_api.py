"""GET /api/v1/filesystem/browse 端点的最小集成测试.

跑在已存在的共享测试 DB 上 — 只覆盖鉴权相关的最小烟测; 越权 / symlink / dotfile
等核心场景由 ``tests/unit/test_filesystem_browser.py`` 的单测覆盖 (数据库无关,
跑得快、隔离干净).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient


@pytest.mark.asyncio(loop_scope="session")
async def test_browse_requires_auth(client: AsyncClient) -> None:
    """无 token 调用受保护端点 → 4xx."""
    response = await client.get("/api/filesystem/browse", params={"path": "/kubeai/home"})
    assert response.status_code in (401, 403)
