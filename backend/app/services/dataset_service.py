from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundException
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AuditAction, ResourceType
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.integrations.minio.client import MinIOClient

logger = logging.getLogger(__name__)


class DatasetService:
    def __init__(self, db: AsyncSession, minio_client: MinIOClient):
        self.db = db
        self.minio = minio_client

    async def create_dataset(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None = None,
        audit_context: dict[str, Any] | None = None,
    ) -> Dataset:
        dataset = Dataset(
            name=name,
            description=description,
            tenant_id=tenant_id,
            created_by=user_id,
        )
        self.db.add(dataset)
        await self.db.flush()
        await self.db.refresh(dataset)

        if audit_context:
            await self._log_audit(
                action=AuditAction.CREATE,
                resource_type=ResourceType.DATASET,
                resource_id=str(dataset.id),
                detail={"name": dataset.name},
                tenant_id=tenant_id,
                **audit_context,
            )

        return dataset

    async def upload_files_to_version(
        self,
        tenant_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        files: list[Any],
    ) -> list[dict[str, Any]]:
        await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)

        await asyncio.to_thread(self.minio.ensure_bucket, tenant_id)

        results: list[dict[str, Any]] = []
        total_size = 0
        prefix = f"datasets/{dataset_id}/v{version.version_number}/"

        for file in files:
            object_name = f"{prefix}{file.filename}"
            content = await file.read()
            size = len(content)

            await asyncio.to_thread(
                self.minio.upload_stream,
                tenant_id,
                object_name,
                BytesIO(content),
                size,
                file.content_type or "application/octet-stream",
            )

            results.append(
                {
                    "file_name": file.filename,
                    "object_name": object_name,
                    "size_bytes": size,
                    "content_type": file.content_type or "application/octet-stream",
                }
            )
            total_size += size

        version.file_count += len(files)
        version.total_size_bytes += total_size
        await self.db.flush()
        await self.db.refresh(version)

        return results

    async def create_version(
        self,
        tenant_id: uuid.UUID,
        dataset_id: uuid.UUID,
        user_id: uuid.UUID,
        description: str | None = None,
    ) -> DatasetVersion:
        await self._get_dataset_or_fail(dataset_id, tenant_id)

        max_ver = await self.db.execute(
            select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id == dataset_id)
        )
        next_number = (max_ver.scalar() or 0) + 1

        version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=next_number,
            description=description,
            storage_path=f"datasets/{dataset_id}/v{next_number}/",
            file_count=0,
            total_size_bytes=0,
            created_by=user_id,
        )
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(version)
        return version

    async def get_dataset(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> Dataset:
        return await self._get_dataset_or_fail(dataset_id, tenant_id)

    async def list_datasets(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> tuple[list[Dataset], int]:
        query = select(Dataset).options(selectinload(Dataset.versions)).where(Dataset.tenant_id == tenant_id)
        if keyword:
            query = query.where(Dataset.name.ilike(f"%{keyword}%"))

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(Dataset.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def delete_dataset(
        self,
        dataset_id: uuid.UUID,
        tenant_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)

        objects = await asyncio.to_thread(self.minio.list_objects, tenant_id, f"datasets/{dataset_id}/")
        if objects:
            await asyncio.to_thread(self.minio.delete_objects, tenant_id, [o["object_name"] for o in objects])

        if audit_context:
            await self._log_audit(
                action=AuditAction.DELETE,
                resource_type=ResourceType.DATASET,
                resource_id=str(dataset.id),
                detail={"name": dataset.name},
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.delete(dataset)
        await self.db.flush()

    async def _get_dataset_or_fail(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> Dataset:
        result = await self.db.execute(
            select(Dataset)
            .options(selectinload(Dataset.versions))
            .where(Dataset.id == dataset_id, Dataset.tenant_id == tenant_id)
        )
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise NotFoundException("数据集不存在")
        return dataset

    async def _get_version_or_fail(self, version_id: uuid.UUID, dataset_id: uuid.UUID) -> DatasetVersion:
        result = await self.db.execute(
            select(DatasetVersion).where(DatasetVersion.id == version_id, DatasetVersion.dataset_id == dataset_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            raise NotFoundException("数据集版本不存在")
        return version

    async def _log_audit(
        self,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: str,
        detail: dict[str, Any] | None = None,
        tenant_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> None:
        audit_svc = AuditService(self.db)
        await audit_svc.log_action(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            tenant_id=tenant_id,
            **kwargs,
        )
