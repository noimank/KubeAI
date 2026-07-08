from __future__ import annotations

import logging
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictException, NotFoundException
from app.integrations.base import sanitize_k8s_name
from app.integrations.storage.filesystem import FileSystemStorage
from app.models.annotation import AnnotationProject
from app.models.dataset import Dataset, DatasetFile, DatasetVersion
from app.models.enums import AuditAction, ResourceType
from app.models.registered_model import ModelVersion
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SortByName = Literal["file_name", "file_size", "uploaded_at"]
SortDirName = Literal["asc", "desc"]


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

    async def upload_files_to_version(
        self,
        tenant_id: uuid.UUID,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        files: list[Any],
        user_id: uuid.UUID,
    ) -> list[DatasetFile]:
        """写入文件并落 DB 行. 同名重传整体拒绝 (整批不写).

        返回写入的 DatasetFile ORM 行 (前端无需再 list 即可拿到 file_id).
        """
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        rows: list[DatasetFile] = []
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
            row = DatasetFile(
                version_id=version.id,
                dataset_id=dataset.id,
                tenant_id=tenant_id,
                file_name=info["file_name"],
                relative_path=info["file_name"],
                file_size=info["size_bytes"],
                content_type=info["content_type"],
                uploaded_by=user_id,
            )
            self.db.add(row)
            rows.append(row)

        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException("文件上传失败, 存在同名文件, 请先删除再上传") from exc

        await self._recompute_version_aggregates(version)
        await self.db.commit()
        await self.db.refresh(version)
        for r in rows:
            await self.db.refresh(r)
        return rows

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
        await self._check_dataset_references(dataset_id)
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
        file_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> None:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        file_row = await self.db.execute(
            select(DatasetFile).where(
                DatasetFile.id == file_id,
                DatasetFile.version_id == version_id,
                DatasetFile.tenant_id == tenant_id,
            )
        )
        row = file_row.scalar_one_or_none()
        if not row:
            raise NotFoundException("文件不存在")

        deleted = await self.storage.delete_file(
            tenant_name=tenant_name,
            dataset_name=dataset.name,
            version_number=version.version_number,
            filename=row.file_name,
        )
        if not deleted:
            # 物理文件已不存在, 但 DB 行仍在. 直接清理 DB 行 (reconcile 时不会再恢复).
            logger.warning("dataset_files row %s points to missing disk file, cleaning up", row.id)

        await self.db.delete(row)
        await self._recompute_version_aggregates(version)
        await self.db.commit()

    async def list_version_files(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 50,
        sort_by: SortByName = "file_name",
        sort_dir: SortDirName = "asc",
    ) -> tuple[list[DatasetFile], int, set[str]]:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)

        sort_col = {
            "file_name": DatasetFile.file_name,
            "file_size": DatasetFile.file_size,
            "uploaded_at": DatasetFile.uploaded_at,
        }[sort_by]
        order = sort_col.asc() if sort_dir == "asc" else sort_col.desc()

        # Annotations live under <version_dir>/annotations/<file>.json; filesystem is the
        # source of truth (AnnotationTask.result was removed for that reason).
        tenant_name = await self._get_tenant_name(tenant_id)
        annotated = await self._scan_annotated_file_names(tenant_name, dataset.name, version.version_number)

        total = (
            await self.db.execute(
                select(func.count()).select_from(DatasetFile).where(DatasetFile.version_id == version_id)
            )
        ).scalar_one()

        rows = (
            (
                await self.db.execute(
                    select(DatasetFile)
                    .where(DatasetFile.version_id == version_id)
                    .order_by(order)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            .scalars()
            .all()
        )

        return list(rows), total, annotated

    async def _scan_annotated_file_names(self, tenant_name: str, dataset_name: str, version_number: int) -> set[str]:
        """Return basenames of files that have an annotations/<file>.json sibling."""
        import asyncio

        ann_dir = self.storage._version_dir(tenant_name, dataset_name, version_number) / "annotations"

        def _scan() -> set[str]:
            if not ann_dir.exists():
                return set()
            return {p.stem for p in ann_dir.iterdir() if p.is_file() and p.suffix == ".json"}

        return await asyncio.to_thread(_scan)

    async def get_version_stats(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)

        cnt, total = (
            await self.db.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(DatasetFile.file_size), 0),
                ).where(DatasetFile.version_id == version_id)
            )
        ).one()

        dist_rows = (
            await self.db.execute(
                select(
                    DatasetFile.file_name,
                    DatasetFile.file_size,
                ).where(DatasetFile.version_id == version_id)
            )
        ).all()

        tenant_name = await self._get_tenant_name(tenant_id)
        annotated = await self._scan_annotated_file_names(tenant_name, dataset.name, version.version_number)

        return {
            "version_id": str(version.id),
            "version_number": version.version_number,
            "file_count": int(cnt or 0),
            "total_size_bytes": int(total or 0),
            "file_type_distribution": self._compute_file_type_distribution(
                [{"file_name": name, "size_bytes": sz} for name, sz in dist_rows]
            ),
            "annotated_count": len(annotated & {name for name, _ in dist_rows}),
        }

    async def reconcile_version_files(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> dict[str, Any]:
        """扫盘 vs DB 对比. INSERT 缺失, 不 DELETE 物理行 (只 WARN).

        仅供 ad-hoc 排查; 不挂 endpoint 不调度.
        """
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(version_id, dataset_id)
        tenant_name = await self._get_tenant_name(tenant_id)

        on_disk = await self.storage._scan_disk_files(
            tenant_name=tenant_name,
            dataset_name=dataset.name,
            version_number=version.version_number,
        )
        disk_by_name = {f["file_name"]: f for f in on_disk}

        rows = (await self.db.execute(select(DatasetFile).where(DatasetFile.version_id == version_id))).scalars().all()
        db_names = {r.file_name for r in rows}

        missing_in_db: list[dict[str, Any]] = []
        for name, info in disk_by_name.items():
            if name in db_names:
                continue
            missing_in_db.append(info)
            stmt = (
                pg_insert(DatasetFile)
                .values(
                    version_id=version_id,
                    dataset_id=dataset.id,
                    tenant_id=tenant_id,
                    file_name=name,
                    relative_path=name,
                    file_size=info["size_bytes"],
                    content_type=info["content_type"],
                )
                .on_conflict_do_nothing(index_elements=["version_id", "relative_path"])
            )
            await self.db.execute(stmt)

        missing_on_disk = [r.file_name for r in rows if r.file_name not in disk_by_name]
        for name in missing_on_disk:
            logger.warning(
                "dataset_files row %s for %s references missing disk file %s",
                next(r.id for r in rows if r.file_name == name),
                version_id,
                name,
            )

        if missing_in_db:
            await self._recompute_version_aggregates(version)
            await self.db.commit()

        return {
            "inserted": len(missing_in_db),
            "missing_on_disk": missing_on_disk,
            "physical_total": len(on_disk),
            "db_total": len(rows),
        }

    async def get_file_download_url(
        self,
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        file_name: str,
        tenant_id: uuid.UUID,
    ) -> str:
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

    async def _recompute_version_aggregates(self, version: DatasetVersion) -> None:
        cnt, total = (
            await self.db.execute(
                select(
                    func.count(),
                    func.coalesce(func.sum(DatasetFile.file_size), 0),
                ).where(DatasetFile.version_id == version.id)
            )
        ).one()
        version.file_count = int(cnt or 0)
        version.total_size_bytes = int(total or 0)

    async def _check_dataset_references(self, dataset_id: uuid.UUID) -> None:
        """删除前校验数据集是否仍被其他资源引用, 给出具体引用来源而非内部服务器错误."""
        references: list[tuple[type[Any], str]] = [
            (TrainingJob, "训练任务"),
            (AnnotationProject, "标注项目"),
            (ModelVersion, "模型版本"),
        ]
        blockers: list[str] = []
        for model, label in references:
            count = (
                await self.db.execute(select(func.count()).select_from(model).where(model.dataset_id == dataset_id))
            ).scalar_one()
            if count:
                blockers.append(f"{count} 个{label}")
        if blockers:
            raise ConflictException(f"该数据集已被以下资源引用, 无法删除: {', '.join(blockers)}")

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
