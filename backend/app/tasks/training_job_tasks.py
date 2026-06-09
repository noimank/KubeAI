from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.taskiq_app import broker
from app.core.ws_pubsub import publish_ws_event
from app.models.enums import TrainingJobStatus
from app.models.training_job import TrainingJob
from app.services.training_job_service import TrainingJobService

logger = structlog.get_logger(__name__)


async def _mark_retrying(job_id: str, tenant_id: str, error: str) -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(TrainingJob).where(
                TrainingJob.id == uuid.UUID(job_id),
                TrainingJob.tenant_id == uuid.UUID(tenant_id),
            )
        )
        job = result.scalar_one_or_none()
        if job is None or job.status == TrainingJobStatus.STOPPED:
            return
        job.status = TrainingJobStatus.PENDING
        job.error_message = f"提交失败, 正在重试: {error}"
        await db.commit()


async def _mark_failed(job_id: str, tenant_id: str, error: str) -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(TrainingJob).where(
                TrainingJob.id == uuid.UUID(job_id),
                TrainingJob.tenant_id == uuid.UUID(tenant_id),
            )
        )
        job = result.scalar_one_or_none()
        if job is None or job.status == TrainingJobStatus.STOPPED:
            return
        old_status = job.status
        job.status = TrainingJobStatus.FAILED
        job.error_message = error
        job.finished_at = datetime.now(UTC)
        await db.commit()
        await publish_ws_event(
            tenant_id=job.tenant_id,
            event="training.status_changed",
            payload={"id": str(job.id), "old_status": old_status, "new_status": TrainingJobStatus.FAILED.value},
        )


@broker.task(task_name="app.tasks.training_job.submit")
async def submit_training_job_task(job_id: str, tenant_id: str) -> dict[str, Any]:
    """提交训练任务到 Volcano (async-native, 由 Taskiq worker 执行).

    手动管理重试循环, 确保重试耗尽后正确标记为 FAILED.
    """
    max_attempts = settings.TASK_MAX_RETRIES
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        try:
            async with async_session_factory() as db:
                svc = TrainingJobService(db)
                await svc.execute_training_job_submission(uuid.UUID(job_id), uuid.UUID(tenant_id))
            return {"job_id": job_id, "status": "submitted"}
        except Exception as exc:
            last_error = str(exc)
            logger.warning(
                "submit_training_job_error",
                job_id=job_id,
                attempt=attempt,
                max_attempts=max_attempts,
                error=last_error,
            )
            if attempt < max_attempts:
                await _mark_retrying(job_id, tenant_id, last_error)
                await asyncio.sleep(settings.TASK_RETRY_BACKOFF_SECONDS)
            else:
                await _mark_failed(job_id, tenant_id, f"提交失败(已重试{max_attempts}次): {last_error}")
                raise

    return {"job_id": job_id, "status": "failed"}


@broker.task(task_name="app.tasks.training_job.stop")
async def stop_training_job_task(job_id: str, tenant_id: str) -> dict[str, Any]:
    """停止训练任务 — 删除 K8s Volcano VCJob (由 Taskiq worker 执行, best-effort)."""
    try:
        async with async_session_factory() as db:
            svc = TrainingJobService(db)
            await svc.execute_training_job_stop(uuid.UUID(job_id), uuid.UUID(tenant_id))
    except Exception as exc:
        logger.error("stop_training_job_error", job_id=job_id, error=str(exc))
        # Best-effort: VCJob 可能已被手动删除或资源清理器后续会处理
        # 不重新抛出, 避免 Taskiq 无限重试

    return {"job_id": job_id, "status": "stopped"}


@broker.task(task_name="app.tasks.training_job.delete")
async def delete_training_job_task(vcjob_name: str, namespace: str) -> dict[str, Any]:
    """删除训练任务 K8s 资源 (由 Taskiq worker 执行, DB 记录已由 API 同步删除)."""
    try:
        async with async_session_factory() as db:
            svc = TrainingJobService(db)
            await svc.execute_training_job_delete(vcjob_name or None, namespace)
    except Exception as exc:
        logger.error("delete_training_job_error", vcjob_name=vcjob_name, error=str(exc))
        # Best-effort: 资源清理器最终会处理孤儿 VCJob

    return {"vcjob_name": vcjob_name, "status": "deleted"}


async def enqueue_submit_training_job(job_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """将训练任务提交入队 (从 API endpoint 调用)."""
    await submit_training_job_task.kiq(str(job_id), str(tenant_id))


async def enqueue_stop_training_job(job_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """将训练任务停止入队 (从 API endpoint 调用)."""
    await stop_training_job_task.kiq(str(job_id), str(tenant_id))


async def enqueue_delete_training_job(vcjob_name: str | None, namespace: str) -> None:
    """将训练任务 K8s 资源删除入队 (从 API endpoint 调用)."""
    await delete_training_job_task.kiq(vcjob_name or "", namespace)
