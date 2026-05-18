import logging
from typing import Any, cast

import httpx

from app.core.config import settings
from app.integrations.base import sanitize_k8s_name

logger = logging.getLogger(__name__)


class HarborClient:
    def __init__(self) -> None:
        self.base_url = settings.HARBOR_URL.rstrip("/")
        self.username = settings.HARBOR_USERNAME
        self.password = settings.HARBOR_PASSWORD
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            auth=(self.username, self.password),
            timeout=httpx.Timeout(10.0, connect=5.0),
            verify=False,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def health_check(self) -> bool:
        try:
            resp = await self._client.get("/api/v2.0/systeminfo")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def ensure_project(self, project_name: str) -> dict[str, Any]:
        existing = await self.get_project(project_name)
        if existing:
            return existing

        resp = await self._client.post(
            "/api/v2.0/projects",
            json={"project_name": project_name, "public": False},
        )
        if resp.status_code in (201, 409):
            return (await self.get_project(project_name)) or {}
        resp.raise_for_status()
        return {}

    async def get_project(self, project_name: str) -> dict[str, Any] | None:
        resp = await self._client.get(
            "/api/v2.0/projects",
            params={"name": project_name},
        )
        if resp.status_code != 200:
            return None
        projects = resp.json()
        for p in projects:
            if p.get("name") == project_name:
                return cast("dict[str, Any]", p)
        return None

    def make_harbor_image_ref(self, tenant_name: str, name: str, tag: str) -> str:
        project = f"{settings.HARBOR_PROJECT_PREFIX}{sanitize_k8s_name(tenant_name)}"
        harbor_host = self.base_url.replace("http://", "").replace("https://", "")
        return f"{harbor_host}/{project}/{name}:{tag}"

    def make_harbor_dockerconfig(self) -> dict[str, str]:
        import base64
        import json

        harbor_host = self.base_url.replace("http://", "").replace("https://", "")
        auth_str = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        docker_config = {
            "auths": {
                harbor_host: {"auth": auth_str},
            }
        }
        return {"config.json": json.dumps(docker_config)}
