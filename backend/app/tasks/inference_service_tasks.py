from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.taskiq_app import broker, interval_to_cron
from app.core.ws_pubsub import publish_ws_event
from app.models.enums import InferenceServiceStatus
from app.models.inference_service import InferenceService
from app.services.inference_service import InferenceServiceService

logger = structlog.get_logger(__name__)


async def _mark_retrying(service_id: str, tenant_id: str, error: str) -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(InferenceService).where(
                InferenceService.id == uuid.UUID(service_id),
                InferenceService.tenant_id == uuid.UUID(tenant_id),
            )
        )
        svc = result.scalar_one_or_none()
        if svc is None or svc.status == InferenceServiceStatus.STOPPED:
            return
        old_status = svc.status
        svc.status = InferenceServiceStatus.PENDING
        svc.error_message = f"部署失败, 正在重试: {error}"
        await db.commit()
        if old_status != svc.status:
            await publish_ws_event(
                tenant_id=svc.tenant_id,
                event="inference.status_changed",
                payload={"id": str(svc.id), "old_status": old_status, "new_status": svc.status},
            )


async def _mark_failed(service_id: str, tenant_id: str, error: str) -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(InferenceService).where(
                InferenceService.id == uuid.UUID(service_id),
                InferenceService.tenant_id == uuid.UUID(tenant_id),
            )
        )
        svc = result.scalar_one_or_none()
        if svc is None or svc.status == InferenceServiceStatus.STOPPED:
            return
        old_status = svc.status
        svc.status = InferenceServiceStatus.FAILED
        svc.error_message = error
        service = InferenceServiceService(db)
        await service._send_failure_notification(svc)
        await db.commit()
        if old_status != svc.status:
            await publish_ws_event(
                tenant_id=svc.tenant_id,
                event="inference.status_changed",
                payload={"id": str(svc.id), "old_status": old_status, "new_status": svc.status},
            )


@broker.task(
    task_name="app.tasks.inference_service.deploy",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def deploy_inference_service_task(service_id: str, tenant_id: str) -> dict[str, Any]:
    """部署推理服务 (async-native, 由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = InferenceServiceService(db)
            await svc.deploy_inference_service(uuid.UUID(service_id), uuid.UUID(tenant_id))
    except Exception as exc:
        logger.warning("deploy_inference_service_error", service_id=service_id, error=str(exc))
        await _mark_retrying(service_id, tenant_id, str(exc))
        raise

    return {"service_id": service_id, "status": "submitted"}


@broker.task(
    task_name="app.tasks.inference_service.sync_statuses",
    schedule=[{"cron": interval_to_cron(settings.INFERENCE_SERVICE_STATUS_SYNC_INTERVAL_SECONDS)}],
)
async def sync_inference_service_statuses_task(limit: int = 200) -> dict[str, Any]:
    """定时同步非终态推理服务的 K8s 状态."""
    async with async_session_factory() as db:
        svc = InferenceServiceService(db)
        synced_count = await svc.sync_non_terminal_inference_services(limit=limit)

    return {"synced_count": synced_count}


async def enqueue_inference_service_deploy(service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """将推理服务部署任务入队 (从 API endpoint 调用)."""
    await deploy_inference_service_task.kiq(str(service_id), str(tenant_id))
