from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.taskiq_app import broker, interval_to_cron
from app.models.enums import TuningStudyStatus
from app.models.tuning import TuningStudy, TuningTrial
from app.services.tuning_service import TuningService

logger = structlog.get_logger(__name__)


@broker.task(
    task_name="app.tasks.tuning.drive",
    schedule=[{"cron": interval_to_cron(settings.TUNING_DRIVE_INTERVAL_SECONDS)}],
)
async def drive_tuning_studies_task() -> dict[str, Any]:
    """兜底驱动所有 RUNNING 调优任务 (safety-net).

    主路径为 trial job 终态事件触发的 finalize_trial_task; 此处仅覆盖 watcher 漏掉的事件
    与补发新 trial. 每个 study 投递独立 drive_study_task (per-study Redis 锁保证 study 内串行).
    """
    async with async_session_factory() as db:
        result = await db.execute(select(TuningStudy.id).where(TuningStudy.status == TuningStudyStatus.RUNNING.value))
        study_ids = [row[0] for row in result.all()]

    for study_id in study_ids:
        await enqueue_drive_study(study_id)
    return {"status": "ok", "studies": len(study_ids)}


@broker.task(task_name="app.tasks.tuning.drive_study")
async def drive_study_task(study_id: str) -> dict[str, Any]:
    """驱动单个 study 一次 (per-study 锁内 reconcile/prune/complete/spawn).

    由兜底 cron 或 study 创建后立即 kiq 触发; 拿不到锁则跳过 (下一个触发接).
    """
    async with async_session_factory() as db:
        await TuningService(db).drive_study_locked(uuid.UUID(study_id))
    return {"status": "ok", "study_id": study_id}


@broker.task(task_name="app.tasks.tuning.finalize_trial")
async def finalize_trial_task(job_id: str) -> dict[str, Any]:
    """trial job 终态事件入口: 反查所属 study 并驱动其 reconcile + 补发.

    非 tuning 任务 (无对应 trial 行) → no-op. per-study 锁串行化, 重复 kiq 幂等.
    """
    job_uuid = uuid.UUID(job_id)
    async with async_session_factory() as db:
        result = await db.execute(select(TuningTrial.study_id).where(TuningTrial.training_job_id == job_uuid))
        study_id = result.scalar_one_or_none()

    if study_id is not None:
        await enqueue_drive_study(study_id)
    return {"status": "ok", "job_id": job_id, "study_id": str(study_id) if study_id else None}


async def enqueue_drive_study(study_id: uuid.UUID) -> None:
    """投递单个 study 驱动 (从 cron / study 创建 / finalize_trial 调用)."""
    await drive_study_task.kiq(str(study_id))


async def enqueue_finalize_trial(job_id: uuid.UUID) -> None:
    """trial job 终态时投递收尾 (从 watcher / stop_training_job_record 调用)."""
    await finalize_trial_task.kiq(str(job_id))
