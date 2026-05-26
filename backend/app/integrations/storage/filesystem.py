from __future__ import annotations

import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Any

import aiofiles

from app.core.config import settings
from app.integrations.base import sanitize_k8s_name

logger = logging.getLogger(__name__)


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
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        dir_path = await self.ensure_dir(tenant_name, dataset_name, version_number)
        file_path = dir_path / filename

        async with aiofiles.open(file_path, "wb") as f:
            await f.write(content)

        actual_type = content_type or self._guess_content_type(filename)
        return {
            "file_name": filename,
            "storage_path": str(file_path.relative_to(self._base_path)),
            "size_bytes": len(content),
            "content_type": actual_type,
        }

    async def list_files(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
    ) -> list[dict[str, Any]]:
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
                            "last_modified": stat.st_mtime,
                        }
                    )
            return results

        import asyncio

        return await asyncio.to_thread(_list)

    def get_file_path(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
        filename: str,
    ) -> Path:
        return self._version_dir(tenant_name, dataset_name, version_number) / filename

    async def delete_file(
        self,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
        filename: str,
    ) -> bool:
        file_path = self._version_dir(tenant_name, dataset_name, version_number) / filename
        if not file_path.exists() or not file_path.is_file():
            return False

        import asyncio

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

    async def copy_file(self, src: Path, dst: Path) -> None:
        """复制单个文件。"""
        dst.parent.mkdir(parents=True, exist_ok=True)

        def _copy() -> None:
            shutil.copy2(str(src), str(dst))

        import asyncio

        await asyncio.to_thread(_copy)

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
        import asyncio

        def _make() -> None:
            path.mkdir(parents=True, exist_ok=True)

        await asyncio.to_thread(_make)

    @staticmethod
    async def _rmtree(path: Path) -> None:
        if not path.exists():
            return

        import asyncio

        def _remove() -> None:
            shutil.rmtree(str(path), ignore_errors=True)

        await asyncio.to_thread(_remove)
