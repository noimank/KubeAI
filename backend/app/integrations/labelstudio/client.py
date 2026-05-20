import logging
from typing import Any, cast

import httpx
from label_studio_sdk import AsyncLabelStudio
from label_studio_sdk.types.annotation import Annotation
from label_studio_sdk.types.import_api_request import ImportApiRequest

from app.core.config import settings
from app.core.exceptions import ExternalServiceException

logger = logging.getLogger(__name__)

_LS_IMPORT_BATCH_SIZE = 250


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
        """Import tasks and return [{"id": int, "data": dict}] pairs.

        For Community edition, task IDs are extracted from the import response.
        Falls back to paginated task listing if task IDs are not available.
        """
        try:
            import_requests = [ImportApiRequest(**task) for task in tasks]
            result = await self._sdk.projects.import_tasks(
                id=project_id,
                request=import_requests,
                return_task_ids=True,
            )
            logger.info("labelstudio_import_tasks project=%s count=%s", project_id, len(tasks))

            # Community edition: task_ids returned as extra field in response
            extra = getattr(result, "__pydantic_extra__", None) or {}
            task_ids: list[int] | None = extra.get("task_ids")

            if task_ids and len(task_ids) == len(tasks):
                return [{"id": tid, "data": tasks[i].get("data", {})} for i, tid in enumerate(task_ids)]

            # Fallback: list recently imported tasks via paginated query
            return await self._list_recent_tasks(project_id, len(tasks))
        except ExternalServiceException:
            raise
        except Exception as e:
            raise self._wrap_error("import_tasks", e) from e

    async def _list_recent_tasks(self, project_id: int, count: int) -> list[dict[str, Any]]:
        """List only the most recent tasks from a project via paginated SDK call."""
        project = await self._sdk.projects.get(id=project_id)
        total = project.task_number or 0

        collected: list[dict[str, Any]] = []
        remaining = count
        page = max(1, (total - count) // 100 + 1)

        while remaining > 0:
            page_size = min(100, remaining)
            pager = await self._sdk.tasks.list(  # type: ignore[no-untyped-call]
                project=project_id, page=page, page_size=page_size
            )
            items = []
            async for task in pager:
                if task.id is not None:
                    items.append({"id": task.id, "data": task.data})
            collected.extend(items)
            if len(items) < page_size:
                break
            remaining -= len(items)
            page += 1

        return collected[-count:]

    async def delete_task(self, task_id: int) -> None:
        """Delete a single task from LabelStudio."""
        try:
            await self._sdk.tasks.delete(id=str(task_id))
            logger.info("labelstudio_task_deleted id=%s", task_id)
        except Exception as e:
            logger.warning("labelstudio_delete_task_failed id=%s: %s", task_id, e)

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

    async def create_annotation(self, task_id: int, result: list[dict[str, Any]]) -> Annotation:
        try:
            annotation = await self._sdk.annotations.create(id=task_id, result=result)
            logger.info("labelstudio_annotation_created task=%s id=%s", task_id, annotation.id)
            return cast("Annotation", annotation)
        except ExternalServiceException:
            raise
        except Exception as e:
            raise self._wrap_error("create_annotation", e) from e

    async def list_annotations(self, task_id: int) -> list[Annotation]:
        try:
            annotations = await self._sdk.annotations.list(id=task_id)
            return cast("list[Annotation]", annotations)
        except ExternalServiceException:
            raise
        except Exception as e:
            raise self._wrap_error("list_annotations", e) from e

    async def delete_annotation(self, annotation_id: int) -> None:
        try:
            await self._sdk.annotations.delete(id=annotation_id)
            logger.info("labelstudio_annotation_deleted id=%s", annotation_id)
        except ExternalServiceException:
            raise
        except Exception as e:
            raise self._wrap_error("delete_annotation", e) from e

    async def export_project_annotations(self, project_id: int) -> list[dict[str, Any]]:
        try:
            base_url = settings.LABEL_STUDIO_URL.rstrip("/")
            resp = await self._httpx.get(
                f"{base_url}/api/projects/{project_id}/export",
                params={"exportType": "JSON"},
                headers={"Authorization": f"Token {settings.LABEL_STUDIO_API_TOKEN}"},
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ExternalServiceException("LabelStudio 导出结果格式无效")
            annotations: list[dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    raise ExternalServiceException("LabelStudio 导出结果格式无效")
                annotations.append(item)
            logger.info("labelstudio_export_annotations project=%s count=%s", project_id, len(data))
            return annotations
        except ExternalServiceException:
            raise
        except Exception as e:
            raise self._wrap_error("export_project_annotations", e) from e

    async def close(self) -> None:
        await self._httpx.aclose()
