"""模型文件下载的 HMAC 签名 token — 本地存储版 "presigned URL".

本地文件系统没有对象存储的预签名机制, 这里用 HMAC-SHA256 签发短期 token 模拟:
token = base64url(payload).hexdigest(HMAC(payload)), 下载匿名 GET 端点验签后流式返回文件.
密钥复用 ``settings.SECRET_KEY`` (JWT 也用它), 恒定时间比较防时序攻击, TTL 2h.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import TYPE_CHECKING, Any

from app.core.config import settings

if TYPE_CHECKING:
    import uuid

_TTL_SECONDS = 2 * 60 * 60  # 2h, 与原 MinIO presigned URL 一致


def _sign(b64: str) -> str:
    return hmac.new(settings.SECRET_KEY.encode(), b64.encode(), hashlib.sha256).hexdigest()


def issue_download_token(version_id: uuid.UUID, file_name: str, tenant_id: uuid.UUID) -> str:
    """签发下载 token: payload = {version, file, tenant, exp}, 返回 ``b64.sig``."""
    payload = {
        "v": str(version_id),
        "f": file_name,
        "t": str(tenant_id),
        "exp": int(time.time()) + _TTL_SECONDS,
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = _sign(b64)
    return f"{b64}.{sig}"


def verify_download_token(token: str) -> dict[str, Any]:
    """验签并返回 payload. 失败 (格式错/签名不符/过期/payload 非法) 一律抛 ``ValueError``."""
    try:
        b64, sig = token.split(".", 1)
    except ValueError as e:
        raise ValueError("invalid token format") from e

    if not hmac.compare_digest(sig, _sign(b64)):
        raise ValueError("bad signature")

    pad = "=" * (-len(b64) % 4)
    try:
        payload: dict[str, Any] = json.loads(base64.urlsafe_b64decode(b64 + pad))
    except Exception as e:
        raise ValueError("invalid token payload") from e

    try:
        exp = int(payload["exp"])
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError("invalid token payload") from e
    if int(time.time()) > exp:
        raise ValueError("expired")
    return payload
