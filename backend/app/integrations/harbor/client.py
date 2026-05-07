import logging
from typing import Any

import requests  # type: ignore[import-untyped]

from app.core.config import settings
from app.integrations.base import BaseIntegration, with_retry

logger = logging.getLogger(__name__)


class HarborClient(BaseIntegration):
    """Harbor REST API 客户端"""

    def __init__(self) -> None:
        self.base_url = settings.HARBOR_URL.rstrip("/")
        self.username = settings.HARBOR_USERNAME
        self.password = settings.HARBOR_PASSWORD

    def _get_auth(self) -> tuple[str, str]:
        return (self.username, self.password)

    @with_retry(max_retries=2)
    def health_check(self) -> bool:
        try:
            resp = requests.get(
                f"{self.base_url}/api/v2.0/systeminfo",
                auth=self._get_auth(),
                timeout=5,
                verify=False,
            )
            return resp.status_code == 200
        except requests.RequestException:
            return False

    @with_retry(max_retries=3)
    def ensure_project(self, project_name: str) -> dict[str, Any]:
        existing = self.get_project(project_name)
        if existing:
            return existing

        resp = requests.post(
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

    @with_retry(max_retries=2)
    def get_project(self, project_name: str) -> dict[str, Any] | None:
        resp = requests.get(
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
                return p
        return None

    def make_harbor_image_ref(self, tenant_id: str, name: str, tag: str) -> str:
        project = f"{settings.HARBOR_PROJECT_PREFIX}{tenant_id}"
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
        return {".dockerconfigjson": json.dumps(docker_config)}


harbor_client = HarborClient()
