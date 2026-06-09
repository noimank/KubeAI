from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.taskiq_app import broker
from app.models.algorithm import Algorithm
from app.services.algorithm_service import AlgorithmService

logger = structlog.get_logger(__name__)


@broker.task(
    task_name="app.tasks.algorithm.upload",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def upload_algorithm_task(algo_id: str, tenant_id: str, temp_file_path: str, filename: str) -> dict[str, Any]:
    """上传算法文件 (压缩 + 存储到算法仓库, 由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = AlgorithmService(db)
            await svc.execute_algorithm_upload(
                uuid.UUID(algo_id),
                uuid.UUID(tenant_id),
                temp_file_path,
                filename,
            )
    except Exception as exc:
        logger.warning("upload_algorithm_error", algo_id=algo_id, error=str(exc))
        async with async_session_factory() as db:
            result = await db.execute(select(Algorithm).where(Algorithm.id == uuid.UUID(algo_id)))
            algo = result.scalar_one_or_none()
            if algo:
                algo.status = "failed"
                await db.commit()
        raise

    return {"algo_id": algo_id, "status": "uploaded"}


async def enqueue_algorithm_upload(
    algo_id: uuid.UUID,
    tenant_id: uuid.UUID,
    temp_file_path: str,
    filename: str,
) -> None:
    await upload_algorithm_task.kiq(str(algo_id), str(tenant_id), temp_file_path, filename)
