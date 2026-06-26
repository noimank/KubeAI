"""APISIX forward-auth 通用鉴权助手.

供所有 APISIX forward-auth 资源 (dev_environment / training_job 等) 共享. 鉴权管线
(JWT 解码 / 黑名单 / 用户与租户状态 / 缓存) 全部委托给 ``IdentityResolver``, 本模块只负责
从转发的请求中提取 token 并把结果翻译成 forward-auth 期望的形态:

  * 解析成功 → 返回 ``TokenIdentity``, 端点据此做资源级鉴权并回写 ``X-KubeAI-User``
  * 无 token 或解析失败 → 返回 ``None``, 端点转为 401/403
"""

from __future__ import annotations

import redis.asyncio as aioredis  # noqa: TC002
from fastapi import Request  # noqa: TC002
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: TC002

from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.identity import IdentityResolver, TokenIdentity

COOKIE_NAME = "kubeai_access_token"


def extract_token_from_request(request: Request) -> str | None:
    """Extract JWT from the forwarded request.

    1. Cookie (forwarded by APISIX ``request_headers: [Cookie]``)
    2. Raw Cookie header parse — fallback for ASGI / proxy edge cases
    3. Bearer header — programmatic access
    """
    # 1. Cookie — primary path, forwarding configured in APISIX route
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token.strip()

    # 2. Raw Cookie header parse — fallback for ASGI / proxy edge cases
    raw_cookie = request.headers.get("Cookie", "")
    if raw_cookie:
        for part in raw_cookie.split(";"):
            part = part.strip()
            if part.startswith(COOKIE_NAME + "="):
                token = part[len(COOKIE_NAME) + 1 :]
                if token:
                    return token.strip()

    # 3. Bearer header — programmatic access
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return None


async def resolve_identity_from_request(
    request: Request,
    db: AsyncSession,
    redis: aioredis.Redis | None = None,
) -> TokenIdentity | None:
    """解析转发请求中的 access token 为 ``TokenIdentity``.

    无 token 或解析失败 (过期 / 黑名单 / 用户禁用 / 租户禁用) 均返回 None.
    forward-auth 端点据此区分: 无 token → 401, 有 token 但失败 → 401/403.
    """
    token = extract_token_from_request(request)
    if not token:
        return None
    try:
        return await IdentityResolver(redis).resolve(token, db)
    except (UnauthorizedException, ForbiddenException):
        return None
