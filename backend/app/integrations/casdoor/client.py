import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceException

logger = logging.getLogger(__name__)

# KubeAI 应用在 Casdoor 侧约定的角色名前缀, 登录读取与反向推送共用此契约
KUBEAI_ROLE_PREFIX = "kubeai_"


class CasdoorClient:
    """Casdoor 管理 API 客户端.

    以应用自身身份认证 (clientId/clientSecret HTTP Basic), 权限等同应用所属
    组织的管理员, 可读写该组织内的用户与角色.
    """

    def __init__(self) -> None:
        self._httpx = httpx.AsyncClient(
            base_url=settings.OIDC_ISSUER.rstrip("/"),
            auth=(settings.OIDC_CLIENT_ID, settings.OIDC_CLIENT_SECRET),
            timeout=30,
        )

    async def get_kubeai_roles(self) -> list[dict[str, Any]]:
        """返回名称带 kubeai_ 前缀的角色对象 (含 users 数组, 即成员 "org/username" 列表)."""
        data = await self._request("GET", "/api/get-roles")
        if not isinstance(data, list):
            raise ExternalServiceException("Casdoor /api/get-roles 返回数据格式异常")
        return [r for r in data if isinstance(r, dict) and str(r.get("name", "")).startswith(KUBEAI_ROLE_PREFIX)]

    async def get_user_by_ref(self, ref: str) -> dict[str, Any] | None:
        """按 OIDC sub 反查用户. 该值随 Casdoor 版本/配置可能是用户 id 而非 owner/name,
        此接口对两种形态都能定位; 用户不存在时返回 None."""
        data = await self._request("GET", "/api/get-user", params={"userId": ref})
        return data if isinstance(data, dict) else None

    async def update_role(self, role: dict[str, Any]) -> None:
        """整体更新角色对象 (Casdoor 以传入对象替换原记录, 须携带读到的完整字段).

        ?id= 查询参数为必传 — 缺失时 Casdoor 服务端切片越界 panic, 返回 HTML 错误页.
        """
        await self._request("POST", "/api/update-role", params={"id": f"{role['owner']}/{role['name']}"}, json=role)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        resp = await self._httpx.request(method, path, **kwargs)
        if resp.status_code != 200:
            raise ExternalServiceException(f"Casdoor {path} 请求失败: HTTP {resp.status_code}")
        try:
            body = resp.json()
        except ValueError as exc:
            # Casdoor 服务端异常时可能以 HTTP 200 返回 HTML 错误页
            raise ExternalServiceException(f"Casdoor {path} 返回非 JSON 响应: {resp.text[:200]}") from exc
        if body.get("status") != "ok":
            raise ExternalServiceException(f"Casdoor {path} 失败: {body.get('msg')}")
        return body.get("data")

    async def close(self) -> None:
        await self._httpx.aclose()
