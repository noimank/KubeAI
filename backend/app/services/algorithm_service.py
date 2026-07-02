from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, NotFoundException
from app.models.algorithm import Algorithm
from app.models.enums import AuditAction, ResourceType
from app.models.tenant import Tenant
from app.services.algorithm_storage_service import AlgorithmStorageService
from app.services.audit_service import AuditService

logger = logging.getLogger(__name__)


class AlgorithmService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_tenant_name(self, tenant_id: uuid.UUID) -> str:
        result = await self.db.execute(select(Tenant.name).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在")
        return tenant

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

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    async def create_algorithm(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        tags: list[str],
        file_bytes: bytes,
        filename: str,
        audit_context: dict[str, Any] | None = None,
    ) -> Algorithm:
        """创建算法记录并同步处理文件上传."""
        algo = Algorithm(
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            description=description,
            tags=tags,
            source_type="upload",
            status="uploading",
        )
        self.db.add(algo)
        await self.db.flush()
        await self.db.refresh(algo)

        # 压缩并存储到共享卷
        zip_path = _compress_to_zip(file_bytes, filename, algo.id)
        try:
            size_bytes = os.path.getsize(zip_path)
        except OSError:
            size_bytes = 0

        tenant_name = await self._get_tenant_name(tenant_id)
        storage = AlgorithmStorageService(tenant_name)
        storage_path = await storage.upload_algorithm_zip(
            user_id=algo.user_id, algorithm_id=algo.id, file_path=zip_path
        )
        _cleanup_temp(zip_path)

        algo.storage_path = storage_path
        algo.size_bytes = size_bytes
        algo.status = "available"
        await self.db.commit()
        await self.db.refresh(algo)

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPLOAD,
                resource_type=ResourceType.ALGORITHM,
                resource_id=str(algo.id),
                detail={"name": algo.name},
                tenant_id=tenant_id,
                **audit_context,
            )

        return algo

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------
    async def list_algorithms(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        name: str | None = None,
        tag: str | None = None,
        uploader_id: uuid.UUID | None = None,
    ) -> tuple[list[Algorithm], int]:
        base = select(Algorithm).where(Algorithm.tenant_id == tenant_id)

        if name:
            base = base.where(Algorithm.name.ilike(f"%{name}%"))
        if uploader_id:
            base = base.where(Algorithm.user_id == uploader_id)
        if tag:
            # PostgreSQL JSONB contains operator
            base = base.where(Algorithm.tags.contains([tag]))

        count_q = select(func.count()).select_from(base.subquery())
        total = (await self.db.execute(count_q)).scalar_one()

        items_q = base.order_by(Algorithm.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = (await self.db.execute(items_q)).scalars().all()

        return list(items), total

    # ------------------------------------------------------------------
    # Get by id
    # ------------------------------------------------------------------
    async def get_algorithm(self, algorithm_id: uuid.UUID, tenant_id: uuid.UUID) -> Algorithm:
        result = await self.db.execute(
            select(Algorithm).where(Algorithm.id == algorithm_id, Algorithm.tenant_id == tenant_id)
        )
        algo = result.scalar_one_or_none()
        if algo is None:
            raise AppException("算法不存在", status_code=404)
        return algo

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
    async def update_algorithm(
        self,
        algorithm_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
        tags: list[str] | None = None,
        is_admin: bool = False,
        audit_context: dict[str, Any] | None = None,
    ) -> Algorithm:
        algo = await self.get_algorithm(algorithm_id, tenant_id)
        if not is_admin and algo.user_id != user_id:
            raise AppException("无权限编辑此算法", status_code=403)

        if name is not None:
            algo.name = name
        if description is not None:
            algo.description = description
        if tags is not None:
            algo.tags = tags

        await self.db.flush()
        await self.db.refresh(algo)

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ALGORITHM,
                resource_id=str(algo.id),
                detail={"name": algo.name},
                tenant_id=tenant_id,
                **audit_context,
            )

        return algo

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------
    async def delete_algorithm(
        self,
        algorithm_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        is_admin: bool = False,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        algo = await self.get_algorithm(algorithm_id, tenant_id)
        if not is_admin and algo.user_id != user_id:
            raise AppException("无权限删除此算法", status_code=403)

        algo_name = algo.name

        # Delete files from file system first (best-effort)
        try:
            tenant_name = await self._get_tenant_name(tenant_id)
            storage = AlgorithmStorageService(tenant_name)
            await storage.delete_algorithm_files(algo.user_id, algorithm_id)
        except Exception:
            logger.warning("文件系统清理失败: algorithm_id=%s", algorithm_id)

        await self.db.delete(algo)
        await self.db.flush()

        if audit_context:
            await self._log_audit(
                action=AuditAction.DELETE,
                resource_type=ResourceType.ALGORITHM,
                resource_id=str(algorithm_id),
                detail={"name": algo_name},
                tenant_id=tenant_id,
                **audit_context,
            )


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------
def _compress_to_zip(file_content: bytes, filename: str, algo_id: uuid.UUID) -> str:
    """Write uploaded bytes into a temp zip file. Returns the zip path."""
    tmp_dir = tempfile.mkdtemp(prefix=f"algo-{algo_id}")
    tmp_file = os.path.join(tmp_dir, filename)
    with open(tmp_file, "wb") as f:
        f.write(file_content)

    zip_path = os.path.join(tmp_dir, "algorithm.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_file, arcname=filename)
        # If the uploaded file is itself a zip, extract and re-pack entries
        if filename.lower().endswith(".zip"):
            try:
                with zipfile.ZipFile(tmp_file, "r") as src:
                    for name in src.namelist():
                        src.extract(name, tmp_dir)
                        extracted = os.path.join(tmp_dir, name)
                        if not os.path.isdir(extracted):
                            zf.write(extracted, arcname=name)
            except zipfile.BadZipFile:
                pass  # not a real zip, already added as single file

    return zip_path


def _cleanup_temp(zip_path: str) -> None:
    try:
        tmp_dir = os.path.dirname(zip_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass
