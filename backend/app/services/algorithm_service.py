from __future__ import annotations

import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ConflictException, NotFoundException
from app.integrations.storage.filesystem_browser import FilesystemBrowserSecurity
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
    # Create (local upload)
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
        """创建算法记录并同步处理本地 zip 上传."""
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
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"算法名称 '{name}' 已存在, 请更换名称") from exc

        await self.db.refresh(algo)

        zip_path = _compress_local_to_zip(file_bytes, filename, algo.id)
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

        return await self._finalize_algorithm_row(algo, storage_path, size_bytes, audit_context)

    # ------------------------------------------------------------------
    # Create (browser register)
    # ------------------------------------------------------------------
    async def create_algorithm_from_paths(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        username: str,
        name: str,
        description: str | None,
        tags: list[str],
        file_paths: list[str],
        audit_context: dict[str, Any] | None = None,
    ) -> Algorithm:
        """从文件浏览器勾选的源创建算法.

        ``file_paths`` 是 canonical 容器内路径; 通过 :class:`FilesystemBrowserSecurity`
        校验身份首段与防 ``..``/symlink 逃逸后, 把每个源复制到 tempdir 并打成
        ``algorithm.zip`` 落盘 — 存储布局与本地 zip 上传一致, ``download_algorithm``
        行为零变化.
        """
        algo = Algorithm(
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            description=description,
            tags=tags,
            source_type="browser",
            status="uploading",
        )
        self.db.add(algo)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"算法名称 '{name}' 已存在, 请更换名称") from exc
        await self.db.refresh(algo)

        tenant_name = await self._get_tenant_name(tenant_id)
        sec = FilesystemBrowserSecurity(username=username, tenant_name=tenant_name)
        home_root, workspace_root = sec.allowed_roots

        # Pass 1: 解析 + 存在性预校验; 任一失败整笔回滚.
        resolved: list[tuple[Path, str]] = []
        for raw in file_paths:
            path = (raw or "").strip()
            if not path:
                raise AppException("file_paths 不可含空字符串", status_code=400)
            try:
                host, _canonical = sec.resolve_container_path(path)
            except PermissionError as e:
                raise AppException(f"路径越权: {e}", status_code=403) from e
            except ValueError as e:
                raise AppException(f"路径非法: {e}", status_code=400) from e
            if not host.exists():
                raise AppException(f"文件不存在: {path}", status_code=400)
            # arcname: 保留源在 home/workspace 根下的相对层级; 通过容器路径前缀选择 root.
            rel_root = workspace_root if path.startswith("/kubeai/workspace/") else home_root
            try:
                rel = host.relative_to(rel_root).as_posix()
            except ValueError:
                # resolve_container_path 已保证 host 在 root 内; 兜底为 basename.
                rel = host.name
            resolved.append((host, rel))

        zip_path = _pack_paths_to_zip(resolved, algo.id)
        try:
            size_bytes = os.path.getsize(zip_path)
        except OSError:
            size_bytes = 0

        storage = AlgorithmStorageService(tenant_name)
        storage_path = await storage.upload_algorithm_zip(
            user_id=algo.user_id, algorithm_id=algo.id, file_path=zip_path
        )
        _cleanup_temp(zip_path)

        ctx = dict(audit_context or {})
        ctx.setdefault("detail_extra", {"source": "browser", "file_paths": file_paths})
        return await self._finalize_algorithm_row(algo, storage_path, size_bytes, ctx)

    # ------------------------------------------------------------------
    # Shared finalize
    # ------------------------------------------------------------------
    async def _finalize_algorithm_row(
        self,
        algo: Algorithm,
        storage_path: str,
        size_bytes: int,
        audit_context: dict[str, Any] | None = None,
    ) -> Algorithm:
        """把 ``Algorithm`` 行落到 ``available`` 状态并写审计 — 两种创建路径共用."""
        algo.storage_path = storage_path
        algo.size_bytes = size_bytes
        algo.status = "available"
        await self.db.commit()
        await self.db.refresh(algo)

        if audit_context:
            detail = {"name": algo.name, "source_type": algo.source_type}
            extra = audit_context.pop("detail_extra", None)
            if isinstance(extra, dict):
                detail.update(extra)
            await self._log_audit(
                action=AuditAction.UPLOAD,
                resource_type=ResourceType.ALGORITHM,
                resource_id=str(algo.id),
                detail=detail,
                tenant_id=algo.tenant_id,
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

        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"算法名称 '{algo.name}' 已存在, 请更换名称") from exc

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
def _compress_local_to_zip(file_content: bytes, filename: str, algo_id: uuid.UUID) -> str:
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


def _pack_paths_to_zip(sources: list[tuple[Path, str]], algo_id: uuid.UUID) -> str:
    """Copy each ``(host_path, arcname)`` into a temp zip and return its path.

    Files are streamed into the zip with ``ZIP_DEFLATED``; directories are walked
    preserving their layout under the supplied ``arcname``.  Single source whose
    ``arcname`` points at a file is written as a top-level entry.
    """
    tmp_dir = tempfile.mkdtemp(prefix=f"algo-browser-{algo_id}")
    zip_path = os.path.join(tmp_dir, "algorithm.zip")

    def _build() -> None:
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for host, arcname in sources:
                if host.is_file():
                    zf.write(host, arcname=arcname)
                elif host.is_dir():
                    for root, _dirs, files in os.walk(host):
                        rel_root = Path(root).relative_to(host)
                        for fn in files:
                            src = Path(root) / fn
                            dst = (Path(arcname) / rel_root / fn).as_posix()
                            zf.write(src, arcname=dst)
                else:
                    # resolve_container_path + exists 已保证是 file 或 dir; 兜底跳过.
                    continue

    _build()
    return zip_path


def _cleanup_temp(zip_path: str) -> None:
    try:
        tmp_dir = os.path.dirname(zip_path)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass
