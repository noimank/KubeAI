from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.taskiq_app import broker
from app.models.enums import BuildStatus
from app.models.image import Image
from app.services.image_service import ImageService

logger = structlog.get_logger(__name__)


@broker.task(task_name="app.tasks.image.build")
async def build_image_task(image_id: str, tenant_id: str) -> dict[str, Any]:
    """构建自定义镜像 (Harbor + K8s 操作链, 由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = ImageService(db)
            await svc.execute_image_build(uuid.UUID(image_id), uuid.UUID(tenant_id))
    except Exception as exc:
        logger.warning("build_image_error", image_id=image_id, error=str(exc))
        async with async_session_factory() as db:
            result = await db.execute(select(Image).where(Image.id == uuid.UUID(image_id)))
            img = result.scalar_one_or_none()
            if img:
                img.build_status = BuildStatus.FAILED
                await db.commit()
        raise

    return {"image_id": image_id, "status": "submitted"}


@broker.task(task_name="app.tasks.image.rebuild")
async def rebuild_image_task(image_id: str, tenant_id: str) -> dict[str, Any]:
    """重新构建自定义镜像 (清理旧 K8s 资源 + 重新提交, 由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = ImageService(db)
            await svc.execute_image_rebuild(uuid.UUID(image_id), uuid.UUID(tenant_id))
    except Exception as exc:
        logger.warning("rebuild_image_error", image_id=image_id, error=str(exc))
        async with async_session_factory() as db:
            result = await db.execute(select(Image).where(Image.id == uuid.UUID(image_id)))
            img = result.scalar_one_or_none()
            if img:
                from app.models.enums import BuildStatus

                img.build_status = BuildStatus.FAILED
                await db.commit()
        raise

    return {"image_id": image_id, "status": "submitted"}


async def enqueue_image_build(image_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await build_image_task.kiq(str(image_id), str(tenant_id))


async def enqueue_image_rebuild(image_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await rebuild_image_task.kiq(str(image_id), str(tenant_id))
