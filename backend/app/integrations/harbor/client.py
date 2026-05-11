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

    def _get_auth(self) -> tuple[str, str]:
        return (self.username, self.password)

    def health_check(self) -> bool:
        try:
            resp = httpx.get(
                f"{self.base_url}/api/v2.0/systeminfo",
                auth=self._get_auth(),
                timeout=5,
                verify=False,
            )
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    def ensure_project(self, project_name: str) -> dict[str, Any]:
        existing = self.get_project(project_name)
        if existing:
            return existing

        resp = httpx.post(
            f"{self.base_url}/api/v2.0/projects",
            auth=self._get_auth(),
            json={"project_name": project_name, "public": False},
            timeout=10,
            verify=False,
        )
        if resp.status_code in (201, 409):
            return self.get_project(project_name) or {}
        resp.raise_for_status()
        return {}

    def get_project(self, project_name: str) -> dict[str, Any] | None:
        resp = httpx.get(
            f"{self.base_url}/api/v2.0/projects",
            auth=self._get_auth(),
            params={"name": project_name},
            timeout=10,
            verify=False,
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


harbor_client = HarborClient()
