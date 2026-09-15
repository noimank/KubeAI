from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.core.database import async_session_factory
from app.core.taskiq_app import broker
from app.services.annotation_service import AnnotationService

logger = structlog.get_logger(__name__)


# ── Project creation / sync tasks ─────────────────────────────────────────────


@broker.task(task_name="app.tasks.annotation.create_project")
async def create_annotation_project_task(project_id: str, tenant_id: str) -> dict[str, Any]:
    """创建标注项目的任务记录 (由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        svc = AnnotationService(db)
        await svc.execute_project_setup(uuid.UUID(project_id), uuid.UUID(tenant_id))

    return {"project_id": project_id, "status": "completed"}


@broker.task(task_name="app.tasks.annotation.sync_tasks")
async def sync_annotation_project_tasks_task(project_id: str, tenant_id: str) -> dict[str, Any]:
    """同步标注项目任务 (枚举新文件 + 建任务记录, 由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        svc = AnnotationService(db)
        await svc.execute_sync_tasks(uuid.UUID(project_id), uuid.UUID(tenant_id))

    return {"project_id": project_id, "status": "synced"}


async def enqueue_annotation_project_create(project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await create_annotation_project_task.kiq(str(project_id), str(tenant_id))


async def enqueue_annotation_project_sync(project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await sync_annotation_project_tasks_task.kiq(str(project_id), str(tenant_id))
