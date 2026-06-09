from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.core.clients import get_labelstudio_client
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.taskiq_app import broker
from app.core.ws_pubsub import publish_ws_event
from app.services.annotation_service import AnnotationService

logger = structlog.get_logger(__name__)


@broker.task(
    task_name="app.tasks.annotation.run_callback",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def run_annotation_callback_task(project_id: str, tenant_id: str) -> dict[str, Any]:
    """执行标注回流: 导出标注结果 → 创建新数据集版本 → 复制文件 → 写入 annotations.json.

    由 Taskiq worker 异步执行, 避免在 API 请求-响应周期内同步执行耗时文件操作.
    """
    pid = uuid.UUID(project_id)
    tid = uuid.UUID(tenant_id)

    async with async_session_factory() as db:
        ls_client = get_labelstudio_client()
        svc = AnnotationService(db, ls_client)
        await svc.execute_callback(pid, tid)

    # 推送 WebSocket 事件通知前端回流完成
    await publish_ws_event(
        tenant_id=tid,
        event="annotation.callback_completed",
        payload={"project_id": project_id},
    )

    return {"project_id": project_id, "status": "completed"}


async def enqueue_annotation_callback(project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """将标注回流任务入队 (从 API endpoint 或 service 调用)."""
    await run_annotation_callback_task.kiq(str(project_id), str(tenant_id))


# ── Project creation / sync tasks ─────────────────────────────────────────────


@broker.task(
    task_name="app.tasks.annotation.create_project",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def create_annotation_project_task(project_id: str, tenant_id: str) -> dict[str, Any]:
    """创建标注项目的 LabelStudio 资源 + 导入任务 (由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        ls_client = get_labelstudio_client()
        svc = AnnotationService(db, ls_client)
        await svc.execute_project_setup(uuid.UUID(project_id), uuid.UUID(tenant_id))

    return {"project_id": project_id, "status": "completed"}


@broker.task(
    task_name="app.tasks.annotation.sync_tasks",
    retry_on_error=True,
    max_retries=1,
)
async def sync_annotation_project_tasks_task(project_id: str, tenant_id: str) -> dict[str, Any]:
    """同步标注项目任务 (枚举新文件 + 导入 LabelStudio, 由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        ls_client = get_labelstudio_client()
        svc = AnnotationService(db, ls_client)
        await svc.execute_sync_tasks(uuid.UUID(project_id), uuid.UUID(tenant_id))

    return {"project_id": project_id, "status": "synced"}


async def enqueue_annotation_project_create(project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await create_annotation_project_task.kiq(str(project_id), str(tenant_id))


async def enqueue_annotation_project_sync(project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await sync_annotation_project_tasks_task.kiq(str(project_id), str(tenant_id))
