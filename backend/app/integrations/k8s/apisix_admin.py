"""APISIX Admin API transport — shared route push/delete helpers.

Both dev-environment pods and TensorBoard sidecars push routes directly to the
APISIX Admin API. Each caller builds its own payload (path, upstream, plugins
differ); this module owns only the HTTP transport and the shared host-derivation
so the two stay in sync.

Token delivery note (applies to every route built on top of this): the NGINX
``$cookie_xxx`` variable does NOT resolve inside APISIX's ``forward-auth`` plugin,
so callers forward the raw ``Cookie`` header via ``request_headers`` and the
backend reads ``kubeai_access_token`` from it directly.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

_TIMEOUT = httpx.Timeout(10.0)
_HEADERS = {"X-API-KEY": settings.KUBEAI_APISIX_ADMIN_KEY}


def host_from_frontend_url() -> str:
    """APISIX route ``host`` filter — the browser-facing hostname from ``FRONTEND_URL``.

    Routes are host-scoped so a tenant namespace's dynamic route does not shadow
    or get shadowed by routes on other hosts served by the same APISIX instance.
    """
    if settings.FRONTEND_URL and "://" in settings.FRONTEND_URL:
        return urlparse(settings.FRONTEND_URL).hostname or "localhost"
    return "localhost"


async def put_route(route_id: str, payload: dict[str, Any]) -> None:
    """PUT a route to the Admin API. Raises on non-2xx (caller decides retry/skip)."""
    async with httpx.AsyncClient(
        base_url=settings.KUBEAI_APISIX_ADMIN_URL.rstrip("/"),
        headers=_HEADERS,
        timeout=_TIMEOUT,
        http2=False,
    ) as client:
        resp = await client.put(f"/apisix/admin/routes/{route_id}", json=payload)
        resp.raise_for_status()
        if resp.status_code in (200, 201):
            logger.info("apisix_route_created", route_id=route_id)


async def delete_route(route_id: str) -> None:
    """DELETE a route by ID. Never raises — a missing route (404) is the desired
    end state, and callers treat cleanup as best-effort."""
    async with httpx.AsyncClient(
        base_url=settings.KUBEAI_APISIX_ADMIN_URL.rstrip("/"),
        headers=_HEADERS,
        timeout=_TIMEOUT,
        http2=False,
    ) as client:
        resp = await client.delete(f"/apisix/admin/routes/{route_id}")
        logger.info("apisix_route_deleted", route_id=route_id, status=resp.status_code)
