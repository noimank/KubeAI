from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import NotFoundException
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AuditAction, ResourceType
from app.models.tenant import Tenant
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

        await asyncio.to_thread(self.minio.ensure_bucket, tenant_name)

        results: list[dict[str, Any]] = []
        total_size = 0
        prefix = f"datasets/{dataset.name}/v{version.version_number}/"

        for file in files:
            object_name = f"{prefix}{file.filename}"
            content = await file.read()
            size = len(content)

            await asyncio.to_thread(
                self.minio.upload_stream,
                tenant_name,
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

        max_ver = await self.db.execute(
            select(func.max(DatasetVersion.version_number)).where(DatasetVersion.dataset_id == dataset_id)
        )
        next_number = (max_ver.scalar() or 0) + 1

        version = DatasetVersion(
            dataset_id=dataset_id,
            version_number=next_number,
            description=description,
            storage_path=f"datasets/{dataset.name}/v{next_number}/",
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

        prefix = f"datasets/{dataset.name}/v{version.version_number}/"
        objects = await asyncio.to_thread(self.minio.list_objects, tenant_name, prefix)
        if objects:
            await asyncio.to_thread(self.minio.delete_objects, tenant_name, [o["object_name"] for o in objects])

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

        objects = await asyncio.to_thread(self.minio.list_objects, tenant_name, f"datasets/{dataset.name}/")
        if objects:
            await asyncio.to_thread(self.minio.delete_objects, tenant_name, [o["object_name"] for o in objects])

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

    async def list_version_files(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> list[dict[str, Any]]:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)
        prefix = f"datasets/{dataset.name}/v{version.version_number}/"
        objects = await asyncio.to_thread(self.minio.list_objects, tenant_name, prefix)
        return [
            {
                "file_name": obj["object_name"].removeprefix(prefix),
                "size_bytes": obj["size"] or 0,
                "content_type": obj["content_type"] or "application/octet-stream",
                "last_modified": obj.get("last_modified"),
            }
            for obj in objects
        ]

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
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)
        object_name = f"datasets/{dataset.name}/v{version.version_number}/{file_name}"
        return await asyncio.to_thread(self.minio.presigned_get_url, tenant_name, object_name)

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

    async def ensure_dataset_pvc(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        from app.integrations.k8s.namespace import make_namespace_name, namespace_exists
        from app.integrations.k8s.pvc import create_pvc, make_dataset_pvc_name

        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        namespace = make_namespace_name(tenant_name)
        if not await asyncio.to_thread(namespace_exists, namespace):
            from app.core.exceptions import BadRequestException

            raise BadRequestException("租户 K8s 命名空间不存在，请联系管理员")  # noqa: RUF001
        pvc_name = make_dataset_pvc_name(dataset.name, version.version_number)
        mount_path = f"/data/datasets/{dataset.name}/v{version.version_number}"

        size_bytes = version.total_size_bytes or 0
        size_gb = max(1, -(-size_bytes // (1024**3)))
        storage_request = f"{size_gb}Gi"

        pvc = await asyncio.to_thread(create_pvc, namespace, pvc_name, storage_request)

        return {
            "pvc_name": pvc_name,
            "mount_path": mount_path,
            "access_mode": "ReadWriteMany",
            "storage_request": storage_request,
            "pvc_status": pvc.status.phase if pvc.status else "Unknown",
        }

    async def get_dataset_mount_info(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        from app.integrations.k8s.namespace import make_namespace_name
        from app.integrations.k8s.pvc import make_dataset_pvc_name, pvc_exists

        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        namespace = make_namespace_name(tenant_name)
        pvc_name = make_dataset_pvc_name(dataset.name, version.version_number)
        mount_path = f"/data/datasets/{dataset.name}/v{version.version_number}"

        if not await asyncio.to_thread(pvc_exists, namespace, pvc_name):
            raise NotFoundException(message=f"版本 v{version.version_number} 尚未挂载")

        from app.integrations.k8s.pvc import get_pvc

        pvc = await asyncio.to_thread(get_pvc, namespace, pvc_name)

        return {
            "pvc_name": pvc_name,
            "mount_path": mount_path,
            "access_mode": "ReadWriteMany",
            "storage_request": pvc.spec.resources.requests.get("storage", "0Gi"),
            "pvc_status": pvc.status.phase if pvc.status else "Unknown",
            "minio_bucket": tenant_name,
            "minio_prefix": version.storage_path,
        }

    async def delete_dataset_pvc(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> None:
        from app.integrations.k8s.namespace import make_namespace_name
        from app.integrations.k8s.pvc import delete_pvc, make_dataset_pvc_name

        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        namespace = make_namespace_name(tenant_name)
        pvc_name = make_dataset_pvc_name(dataset.name, version.version_number)
        await asyncio.to_thread(delete_pvc, namespace, pvc_name)

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
