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


# ── Shared helpers ────────────────────────────────────────────────────────────


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


# ── Deploy task (initial create) ──────────────────────────────────────────────


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


# ── Start / Stop / Scale / Delete tasks ───────────────────────────────────────


@broker.task(
    task_name="app.tasks.inference_service.start",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def start_inference_service_task(service_id: str, tenant_id: str) -> dict[str, Any]:
    """启动推理服务 K8s 资源 (由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = InferenceServiceService(db)
            await svc.execute_inference_service_start(uuid.UUID(service_id), uuid.UUID(tenant_id))
    except Exception as exc:
        logger.warning("start_inference_service_error", service_id=service_id, error=str(exc))
        await _mark_failed(service_id, tenant_id, f"启动失败: {exc}")
        raise

    return {"service_id": service_id, "status": "started"}


@broker.task(
    task_name="app.tasks.inference_service.stop",
    retry_on_error=True,
    max_retries=1,
)
async def stop_inference_service_task(service_id: str, tenant_id: str) -> dict[str, Any]:
    """停止推理服务 K8s 资源 (由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        svc = InferenceServiceService(db)
        await svc.execute_inference_service_stop(uuid.UUID(service_id), uuid.UUID(tenant_id))

    return {"service_id": service_id, "status": "stopped"}


@broker.task(
    task_name="app.tasks.inference_service.scale",
    retry_on_error=True,
    max_retries=1,
)
async def scale_inference_service_task(service_id: str, tenant_id: str, replicas: int) -> dict[str, Any]:
    """扩缩容推理服务 K8s 资源 (由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        svc = InferenceServiceService(db)
        await svc.execute_inference_service_scale(uuid.UUID(service_id), uuid.UUID(tenant_id), replicas)

    return {"service_id": service_id, "status": "scaled", "replicas": replicas}


@broker.task(
    task_name="app.tasks.inference_service.delete",
    retry_on_error=True,
    max_retries=1,
)
async def delete_inference_service_task(
    service_type: str,
    namespace: str,
    scaling_mode: str,
    kserve_name: str = "",
    k8s_deployment_name: str = "",
    k8s_service_name: str = "",
    canary_kserve_name: str = "",
) -> dict[str, Any]:
    """删除推理服务 K8s 资源 (由 Taskiq worker 执行, DB 记录已由 API 删除)."""
    from app.services.inference_service import InferenceServiceService

    await InferenceServiceService.cleanup_k8s_resources(
        service_type=service_type,
        namespace=namespace,
        scaling_mode=scaling_mode,
        kserve_name=kserve_name or None,
        k8s_deployment_name=k8s_deployment_name or None,
        k8s_service_name=k8s_service_name or None,
        canary_kserve_name=canary_kserve_name or None,
    )

    return {"status": "deleted"}


# ── Canary tasks ──────────────────────────────────────────────────────────────


@broker.task(
    task_name="app.tasks.inference_service.canary_start",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def start_canary_task(service_id: str, tenant_id: str) -> dict[str, Any]:
    """部署金丝雀版本 K8s InferenceService (由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = InferenceServiceService(db)
            await svc.execute_canary_start(uuid.UUID(service_id), uuid.UUID(tenant_id))
    except Exception as exc:
        logger.warning("start_canary_error", service_id=service_id, error=str(exc))
        async with async_session_factory() as db:
            result = await db.execute(select(InferenceService).where(InferenceService.id == uuid.UUID(service_id)))
            svc_obj = result.scalar_one_or_none()
            if svc_obj and svc_obj.canary_status != "none":
                svc_obj.canary_status = "failed"
                svc_obj.error_message = f"金丝雀部署失败: {exc}"
                await db.commit()
        raise

    return {"service_id": service_id, "status": "canary_started"}


@broker.task(
    task_name="app.tasks.inference_service.canary_promote",
    retry_on_error=True,
    max_retries=1,
)
async def promote_canary_task(service_id: str, tenant_id: str) -> dict[str, Any]:
    """提升金丝雀为稳定版本 — K8s 操作 (由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        svc = InferenceServiceService(db)
        await svc.execute_canary_promote(uuid.UUID(service_id), uuid.UUID(tenant_id))

    return {"service_id": service_id, "status": "canary_promoted"}


@broker.task(
    task_name="app.tasks.inference_service.canary_rollback",
    retry_on_error=True,
    max_retries=1,
)
async def rollback_canary_task(service_id: str, tenant_id: str) -> dict[str, Any]:
    """回滚金丝雀版本 — K8s 清理 (由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        svc = InferenceServiceService(db)
        await svc.execute_canary_rollback(uuid.UUID(service_id), uuid.UUID(tenant_id))

    return {"service_id": service_id, "status": "canary_rolled_back"}


# ── Scheduled sync task ───────────────────────────────────────────────────────


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


# ── Enqueue helpers ───────────────────────────────────────────────────────────


async def enqueue_inference_service_deploy(service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await deploy_inference_service_task.kiq(str(service_id), str(tenant_id))


async def enqueue_inference_service_start(service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await start_inference_service_task.kiq(str(service_id), str(tenant_id))


async def enqueue_inference_service_stop(service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await stop_inference_service_task.kiq(str(service_id), str(tenant_id))


async def enqueue_inference_service_scale(service_id: uuid.UUID, tenant_id: uuid.UUID, replicas: int) -> None:
    await scale_inference_service_task.kiq(str(service_id), str(tenant_id), replicas)


async def enqueue_inference_service_delete(
    service_type: str,
    namespace: str,
    scaling_mode: str,
    kserve_name: str | None,
    k8s_deployment_name: str | None,
    k8s_service_name: str | None,
    canary_kserve_name: str | None,
) -> None:
    await delete_inference_service_task.kiq(
        service_type,
        namespace,
        scaling_mode,
        kserve_name or "",
        k8s_deployment_name or "",
        k8s_service_name or "",
        canary_kserve_name or "",
    )


async def enqueue_canary_start(service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await start_canary_task.kiq(str(service_id), str(tenant_id))


async def enqueue_canary_promote(service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await promote_canary_task.kiq(str(service_id), str(tenant_id))


async def enqueue_canary_rollback(service_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    await rollback_canary_task.kiq(str(service_id), str(tenant_id))
