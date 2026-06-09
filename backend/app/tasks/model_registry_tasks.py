from __future__ import annotations

import io
import os
import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.clients import get_minio_client
from app.core.database import async_session_factory
from app.core.taskiq_app import broker
from app.models.enums import ModelVersionStatus
from app.models.registered_model import ModelVersion
from app.models.tenant import Tenant

logger = structlog.get_logger(__name__)


@broker.task(
    task_name="app.tasks.model_registry.upload",
    retry_on_error=True,
    max_retries=2,
)
async def upload_model_files_task(version_id: str, tenant_id: str, temp_dir: str) -> dict[str, Any]:
    """上传模型文件到 MinIO (由 Taskiq worker 执行)."""
    minio = get_minio_client()

    async with async_session_factory() as db:
        result = await db.execute(select(ModelVersion).where(ModelVersion.id == uuid.UUID(version_id)))
        version = result.scalar_one_or_none()
        if not version:
            return {"status": "version_not_found", "version_id": version_id}

        tenant_result = await db.execute(select(Tenant).where(Tenant.id == uuid.UUID(tenant_id)))
        tenant = tenant_result.scalar_one_or_none()
        if not tenant:
            version.status = ModelVersionStatus.FAILED
            await db.commit()
            return {"status": "tenant_not_found"}

        await minio.ensure_bucket(tenant.name)

        uploaded_count = 0
        total_size = 0

        try:
            for entry in os.scandir(temp_dir):
                if entry.is_file():
                    with open(entry.path, "rb") as f:
                        content = f.read()
                    object_name = f"{version.storage_path}/{entry.name}"
                    await minio.upload_stream(
                        tenant_name=tenant.name,
                        object_name=object_name,
                        data=io.BytesIO(content),
                        length=len(content),
                        content_type="application/octet-stream",
                    )
                    total_size += len(content)
                    uploaded_count += 1

            version.file_count = uploaded_count
            version.total_size_bytes = total_size
            version.status = ModelVersionStatus.AVAILABLE
        except Exception as e:
            version.status = ModelVersionStatus.FAILED
            logger.error("upload_model_files_failed", version_id=version_id, error=str(e))
            raise
        finally:
            await db.commit()
            # Clean up temp dir
            try:
                for entry in os.scandir(temp_dir):
                    if entry.is_file():
                        os.remove(entry.path)
                os.rmdir(temp_dir)
            except OSError:
                pass

    return {"version_id": version_id, "status": "uploaded", "file_count": uploaded_count}


@broker.task(
    task_name="app.tasks.model_registry.delete_objects",
    retry_on_error=True,
    max_retries=1,
)
async def delete_model_objects_task(
    tenant_name: str,
    storage_path: str,
    object_names: str = "",
) -> dict[str, Any]:
    """删除 MinIO 模型文件 (由 Taskiq worker 执行, DB 记录已由 API 删除)."""
    minio = get_minio_client()

    if object_names:
        names = object_names.split("\n")
        try:
            await minio.delete_objects(tenant_name, names)
        except Exception as e:
            logger.warning("delete_model_objects_failed", storage_path=storage_path, error=str(e))
    else:
        # List and delete all objects under prefix
        try:
            objects = await minio.list_objects(tenant_name, storage_path)
            if objects:
                names = [o["object_name"] for o in objects]
                await minio.delete_objects(tenant_name, names)
        except Exception as e:
            logger.warning("delete_model_objects_failed", storage_path=storage_path, error=str(e))

    return {"storage_path": storage_path, "status": "deleted"}


async def enqueue_model_files_upload(version_id: uuid.UUID, tenant_id: uuid.UUID, temp_dir: str) -> None:
    await upload_model_files_task.kiq(str(version_id), str(tenant_id), temp_dir)


async def enqueue_model_objects_delete(
    tenant_name: str,
    storage_paths: list[str],
) -> None:
    """Enqueue MinIO cleanup for multiple storage paths."""
    for sp in storage_paths:
        await delete_model_objects_task.kiq(tenant_name, sp, "")
