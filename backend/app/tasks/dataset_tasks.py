from __future__ import annotations

import os
import uuid
from typing import Any

import structlog

from app.core.database import async_session_factory
from app.core.taskiq_app import broker
from app.services.dataset_service import DatasetService

logger = structlog.get_logger(__name__)


@broker.task(
    task_name="app.tasks.dataset.upload_files",
    retry_on_error=True,
    max_retries=1,
)
async def upload_dataset_files_task(version_id: str, tenant_id: str, temp_dir: str) -> dict[str, Any]:
    """上传数据集文件到存储 (由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = DatasetService(db)
            await svc.execute_files_upload(uuid.UUID(version_id), uuid.UUID(tenant_id), temp_dir)
    finally:
        try:
            for entry in os.scandir(temp_dir):
                if entry.is_file():
                    os.remove(entry.path)
            os.rmdir(temp_dir)
        except OSError:
            pass

    return {"version_id": version_id, "status": "uploaded"}


async def enqueue_dataset_files_upload(version_id: uuid.UUID, tenant_id: uuid.UUID, temp_dir: str) -> None:
    await upload_dataset_files_task.kiq(str(version_id), str(tenant_id), temp_dir)
