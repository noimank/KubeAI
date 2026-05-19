import logging
from typing import Any

import httpx
from label_studio_sdk import AsyncLabelStudio

from app.core.config import settings
from app.core.exceptions import ExternalServiceException

logger = logging.getLogger(__name__)


class LabelStudioClient:
    def __init__(self) -> None:
        self._httpx = httpx.AsyncClient(timeout=30)
        self._sdk = AsyncLabelStudio(  # type: ignore[no-untyped-call]
            base_url=settings.LABEL_STUDIO_URL.rstrip("/"),
            api_key=settings.LABEL_STUDIO_API_TOKEN,
            httpx_client=self._httpx,
        )

    def _wrap_error(self, operation: str, e: Exception) -> ExternalServiceException:
        """Convert SDK errors to ExternalServiceException with full context."""
        detail = str(e)
        if hasattr(e, "status_code"):
            detail = f"HTTP {e.status_code}: {detail}"
        if hasattr(e, "body"):
            detail = f"{detail} — {e.body}"
        logger.error("labelstudio_%s_failed: %s", operation, detail, exc_info=True)
        return ExternalServiceException(f"LabelStudio {operation} 失败: {detail}")

    async def create_project(self, title: str, description: str = "", label_config: str = "") -> int:
        try:
            project = await self._sdk.projects.create(
                title=title, description=description or None, label_config=label_config or None
            )
            assert project.id is not None
            logger.info("labelstudio_project_created id=%s title=%s", project.id, title)
            return project.id
        except ExternalServiceException:
            raise
        except Exception as e:
            raise self._wrap_error("create_project", e) from e

    async def import_tasks(self, project_id: int, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            await self._sdk.projects.import_tasks(
                id=project_id,
                request=tasks,
                return_task_ids=True,  # type: ignore[arg-type]
            )
            logger.info("labelstudio_import_tasks project=%s count=%s", project_id, len(tasks))

            # List tasks after import — for Community edition they're available immediately;
            # for non-Community editions the import is async but listing still returns what's ready
            collected: list[dict[str, Any]] = []
            async for task in await self._sdk.tasks.list(project=project_id):  # type: ignore[no-untyped-call]
                if task.id is not None:
                    collected.append({"id": task.id, "data": task.data})
            return collected
        except ExternalServiceException:
            raise
        except Exception as e:
            raise self._wrap_error("import_tasks", e) from e

    async def get_project_stats(self, project_id: int) -> dict[str, Any]:
        try:
            project = await self._sdk.projects.get(id=project_id)
            return {"total": project.task_number or 0, "completed": project.finished_task_number or 0}
        except Exception as e:
            logger.warning("labelstudio_get_stats_failed project=%s: %s", project_id, e)
            return {"total": 0, "completed": 0}

    async def delete_project(self, project_id: int) -> None:
        try:
            await self._sdk.projects.delete(id=project_id)
            logger.info("labelstudio_project_deleted id=%s", project_id)
        except Exception as e:
            logger.warning("labelstudio_delete_project_failed id=%s: %s", project_id, e)

    async def close(self) -> None:
        await self._httpx.aclose()
