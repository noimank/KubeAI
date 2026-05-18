import logging
from typing import Any, cast

import httpx

from app.core.config import settings
from app.core.exceptions import ExternalServiceException

logger = logging.getLogger(__name__)


class LabelStudioClient:
    def __init__(self) -> None:
        self.base_url = settings.LABEL_STUDIO_URL.rstrip("/")
        self.api_token = settings.LABEL_STUDIO_API_TOKEN
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Token {self.api_token}"},
            timeout=30,
        )

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            resp = await self._client.request(method, path, **kwargs)
            resp.raise_for_status()
            if resp.status_code == 204:
                return None
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error("LabelStudio API error: %s %s -> %s", method, path, e.response.text)
            raise ExternalServiceException(f"LabelStudio 请求失败: {e.response.text}") from e
        except httpx.HTTPError as e:
            logger.error("LabelStudio connection error: %s", e)
            raise ExternalServiceException(f"LabelStudio 连接失败: {e}") from e

    async def create_project(self, title: str, description: str = "", label_config: str = "") -> dict[str, Any]:
        return cast(
            "dict[str, Any]",
            await self._request(
                "POST",
                "/api/projects",
                json={"title": title, "description": description, "label_config": label_config},
            ),
        )

    async def import_tasks(self, project_id: int, tasks: list[dict[str, Any]]) -> list[Any]:
        return cast("list[Any]", await self._request("POST", f"/api/projects/{project_id}/import", json=tasks))

    async def get_project(self, project_id: int) -> dict[str, Any]:
        return cast("dict[str, Any]", await self._request("GET", f"/api/projects/{project_id}"))

    async def list_projects(self) -> list[dict[str, Any]]:
        return cast("list[dict[str, Any]]", await self._request("GET", "/api/projects"))

    async def delete_project(self, project_id: int) -> None:
        await self._request("DELETE", f"/api/projects/{project_id}")

    async def get_project_stats(self, project_id: int) -> dict[str, Any]:
        return cast("dict[str, Any]", await self._request("GET", f"/api/projects/{project_id}/summary"))

    async def close(self) -> None:
        await self._client.aclose()
