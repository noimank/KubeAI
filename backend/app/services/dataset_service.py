from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundException
from app.integrations.base import sanitize_k8s_name
from app.integrations.storage.filesystem import FileSystemStorage
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AuditAction, ResourceType
from app.models.tenant import Tenant
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DatasetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.storage = FileSystemStorage()

    async def _get_tenant_name(self, tenant_id: uuid.UUID) -> str:
        result = await self.db.execute(select(Tenant.name).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在")
        return tenant

    async def create_dataset(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        display_name: str | None = None,
        description: str | None = None,
        audit_context: dict[str, Any] | None = None,
    ) -> Dataset:
        dataset = Dataset(
            name=name,
            display_name=display_name,
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

        await self.db.commit()
        return dataset

    async def execute_files_upload(
        self,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
        temp_dir: str,
    ) -> None:
        """由 Taskiq worker 调用: 上传文件到存储并更新版本统计."""
        from app.models.dataset import DatasetVersion

        result = await self.db.execute(select(DatasetVersion).where(DatasetVersion.id == version_id))
        version = result.scalar_one_or_none()
        if not version:
            return

        dataset = await self._get_dataset_or_fail(version.dataset_id, tenant_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        total_size = 0
        file_count = 0
        for entry in os.scandir(temp_dir):
            if entry.is_file():
                with open(entry.path, "rb") as f:
                    content = f.read()
                await self.storage.upload_file(
                    tenant_name=tenant_name,
                    dataset_name=dataset.name,
                    version_number=version.version_number,
                    filename=entry.name,
                    content=content,
                    content_type="application/octet-stream",
                )
                total_size += len(content)
                file_count += 1

        version.file_count += file_count
        version.total_size_bytes += total_size
        await self.db.flush()
        await self.db.commit()

    async def upload_files_to_version(
        self,
        tenant_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        files: list[Any],
    ) -> list[dict[str, Any]]:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        results: list[dict[str, Any]] = []
        total_size = 0

        for file in files:
            content = await file.read()
            info = await self.storage.upload_file(
                tenant_name=tenant_name,
                dataset_name=dataset.name,
                version_number=version.version_number,
                filename=file.filename,
                content=content,
                content_type=file.content_type or "application/octet-stream",
            )
            results.append(info)
            total_size += info["size_bytes"]

        version.file_count += len(files)
        version.total_size_bytes += total_size
        await self.db.flush()
        await self.db.refresh(version)
        await self.db.commit()

        return results

    async def create_version(
        self,
        tenant_id: uuid.UUID,
        dataset_id: uuid.UUID,
        user_id: uuid.UUID,
        description: str | None = None,
    ) -> DatasetVersion:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        max_ver = await self.db.execute(
            select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id == dataset_id)
        )
        next_number = (max_ver.scalar() or 0) + 1

        storage_path = f"datasets/{sanitize_k8s_name(tenant_name)}/{sanitize_k8s_name(dataset.name)}/v{next_number}/"

        version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=next_number,
            description=description,
            storage_path=storage_path,
            file_count=0,
            total_size_bytes=0,
            created_by=user_id,
        )
        self.db.add(version)
        await self.db.flush()
        await self.db.refresh(version)
        await self.db.commit()
        return version

    async def get_dataset(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> Dataset:
        return await self._get_dataset_or_fail(dataset_id, tenant_id)

    async def list_datasets(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> tuple[list[Dataset], int]:
        query = select(Dataset).options(selectinload(Dataset.versions)).where(Dataset.tenant_id == tenant_id)
        if keyword:
            query = query.where(Dataset.name.ilike(f"%{keyword}%"))
        if start_date:
            query = query.where(Dataset.created_at >= start_date)
        if end_date:
            next_day = end_date + timedelta(days=1)
            query = query.where(Dataset.created_at < next_day)

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(Dataset.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def delete_version(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        await self.storage.delete_version(tenant_name, dataset.name, version.version_number)

        if audit_context:
            await self._log_audit(
                action=AuditAction.DELETE,
                resource_type=ResourceType.DATASET,
                resource_id=str(version_id),
                detail={"dataset_id": str(dataset_id), "version_number": version.version_number},
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.delete(version)
        await self.db.commit()

    async def delete_dataset(
        self,
        dataset_id: uuid.UUID,
        tenant_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        await self.storage.delete_dataset(tenant_name, dataset.name)

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
        await self.db.commit()

    async def delete_file(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        file_name: str,
        tenant_id: uuid.UUID,
    ) -> None:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        file_path = self.storage.get_file_path(tenant_name, dataset.name, version.version_number, file_name)
        if not file_path.exists():
            raise NotFoundException("文件不存在")

        file_size = file_path.stat().st_size
        deleted = await self.storage.delete_file(tenant_name, dataset.name, version.version_number, file_name)
        if not deleted:
            raise NotFoundException("文件删除失败")

        version.file_count = max(0, version.file_count - 1)
        version.total_size_bytes = max(0, version.total_size_bytes - file_size)
        await self.db.flush()
        await self.db.commit()

    async def list_version_files(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)
        return await self.storage.list_files(tenant_name, dataset.name, version.version_number)

    async def get_version_stats(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        files = await self.list_version_files(dataset_id, version_id, tenant_id)
        distribution = self._compute_file_type_distribution(files)
        return {
            "version_id": str(version.id),
            "version_number": version.version_number,
            "file_count": len(files),
            "total_size_bytes": sum(f["size_bytes"] for f in files),
            "file_type_distribution": distribution,
        }

    async def get_file_download_url(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        file_name: str,
        tenant_id: uuid.UUID,
    ) -> str:
        # Validate access
        await self._get_dataset_or_fail(dataset_id, tenant_id)
        await self._get_version_or_fail(version_id, dataset_id)
        return f"/api/datasets/{dataset_id}/versions/{version_id}/files/{file_name}/download"

    async def get_file_path(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        file_name: str,
        tenant_id: uuid.UUID,
    ) -> Path:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)
        return self.storage.get_file_path(tenant_name, dataset.name, version.version_number, file_name)

    def _compute_file_type_distribution(self, files: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ext_counter: dict[str, dict[str, Any]] = {}
        for f in files:
            name = f["file_name"]
            ext = Path(name).suffix.lower() if "." in name else "(无扩展名)"
            if ext not in ext_counter:
                ext_counter[ext] = {"extension": ext, "count": 0, "total_size_bytes": 0}
            ext_counter[ext]["count"] += 1
            ext_counter[ext]["total_size_bytes"] += f["size_bytes"]
        return sorted(ext_counter.values(), key=lambda x: x["count"], reverse=True)

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
