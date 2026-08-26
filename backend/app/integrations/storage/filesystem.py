from __future__ import annotations

import asyncio
import logging
import mimetypes
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles

from app.core.config import settings
from app.integrations.base import sanitize_k8s_name
from app.integrations.storage.path_safety import resolve_within

if TYPE_CHECKING:
    from fastapi import UploadFile

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024  # 1MB


class FileSystemStorage:
    def __init__(self, base_path: str | None = None) -> None:
        self._base_path = Path(base_path or settings.DATASET_BASE_PATH)

    def _version_dir(self, tenant_name: str, dataset_name: str, version_number: int) -> Path:
        return self._base_path / sanitize_k8s_name(tenant_name) / sanitize_k8s_name(dataset_name) / f"v{version_number}"

    def _dataset_dir(self, tenant_name: str, dataset_name: str) -> Path:
        return self._base_path / sanitize_k8s_name(tenant_name) / sanitize_k8s_name(dataset_name)

    async def ensure_dir(self, tenant_name: str, dataset_name: str, version_number: int) -> Path:
        dir_path = self._version_dir(tenant_name, dataset_name, version_number)
        await self._mkdir(dir_path)
        return dir_path

    async def upload_file(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
        filename: str,
        file: UploadFile,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        """流式落盘一个上传文件 (分块 + 大小限额), 返回文件元信息.

        ``filename`` 必须经 :func:`sanitize_filename` 归一化; 此处再做 containment
        校验作为兜底, 任何逃逸目标目录的路径都会被拒绝。
        """
        dir_path = await self.ensure_dir(tenant_name, dataset_name, version_number)
        resolved_base = self._base_path.resolve()
        file_path = resolve_within(dir_path, filename)

        written = 0
        exceeded = False
        async with aiofiles.open(file_path, "wb") as out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                written += len(chunk)
                if written > settings.UPLOAD_MAX_FILE_BYTES:
                    exceeded = True
                    break
                await out.write(chunk)
        if exceeded:
            await asyncio.to_thread(file_path.unlink, missing_ok=True)
            raise ValueError(f"文件超过大小上限 {settings.UPLOAD_MAX_FILE_BYTES} 字节")

        actual_type = content_type or self._guess_content_type(filename)
        return {
            "file_name": filename,
            "storage_path": str(file_path.relative_to(resolved_base)),
            "size_bytes": written,
            "content_type": actual_type,
        }

    async def list_files(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
    ) -> list[dict[str, Any]]:
        """扫描版本目录, 返回 [{file_name, size_bytes, content_type}]."""

        return await self._scan_disk_files(tenant_name, dataset_name, version_number)

    async def _scan_disk_files(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
    ) -> list[dict[str, Any]]:
        """私有: 扫盘. 仅 reconcile 之类离线场景使用, 不应在正常 service list 路径调用."""
        dir_path = self._version_dir(tenant_name, dataset_name, version_number)

        def _list() -> list[dict[str, Any]]:
            if not dir_path.exists():
                return []
            results: list[dict[str, Any]] = []
            for p in sorted(dir_path.iterdir()):
                if p.is_file():
                    stat = p.stat()
                    results.append(
                        {
                            "file_name": p.name,
                            "size_bytes": stat.st_size,
                            "content_type": self._guess_content_type(p.name),
                        }
                    )
            return results

        return await asyncio.to_thread(_list)

    def get_file_path(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
        filename: str,
    ) -> Path:
        # containment 校验: 任何 ``../``、绝对路径、symlink 逃逸都会抛 ValueError
        return resolve_within(self._version_dir(tenant_name, dataset_name, version_number), filename)

    async def delete_file(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
        filename: str,
    ) -> bool:
        file_path = resolve_within(self._version_dir(tenant_name, dataset_name, version_number), filename)
        if not file_path.exists() or not file_path.is_file():
            return False

        await asyncio.to_thread(file_path.unlink)
        return True

    async def delete_version(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
    ) -> None:
        """递归删除版本目录。"""
        dir_path = self._version_dir(tenant_name, dataset_name, version_number)
        await self._rmtree(dir_path)

    async def delete_dataset(
        self,
        tenant_name: str,
        dataset_name: str,
    ) -> None:
        dir_path = self._dataset_dir(tenant_name, dataset_name)
        await self._rmtree(dir_path)

    async def get_file_content(self, file_path: Path) -> bytes:
        async with aiofiles.open(file_path, "rb") as f:
            content: bytes = await f.read()
            return content

    async def write_file(self, file_path: Path, content: bytes) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

    @staticmethod
    def _guess_content_type(filename: str) -> str:
        guessed, _ = mimetypes.guess_type(filename)
        return guessed or "application/octet-stream"

    @staticmethod
    async def _mkdir(path: Path) -> None:
        def _make() -> None:
            path.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(_make)

    @staticmethod
    async def _rmtree(path: Path) -> None:
        if not path.exists():
            return

        def _remove() -> None:
            shutil.rmtree(str(path), ignore_errors=True)

        await asyncio.to_thread(_remove)
