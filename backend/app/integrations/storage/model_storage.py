from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles

from app.core.config import settings
from app.integrations.base import sanitize_k8s_name

if TYPE_CHECKING:
    from fastapi import UploadFile

logger = logging.getLogger(__name__)

_CHUNK_SIZE = 1024 * 1024  # 1MB

# 容器内允许注册模型文件的挂载前缀 (与 kubeai_volumes / job_builder 一致):
# home = 用户个人目录, workspace = 租户共享工作空间.
HOME_PREFIX = "/kubeai/home"
WORKSPACE_PREFIX = "/kubeai/workspace"


class ModelStorage:
    """模型版本的本地文件系统存储.

    磁盘布局: ``{MODEL_BASE_PATH}/{sanitize(tenant)}/{storage_path}/<files>``, 其中
    ``storage_path`` 为 ``models/<name>/v<N>`` (DB 字段原样, 不含 tenant — tenant 段在此拼).
    模拟 S3 bucket/object 层级, 但用本地目录隔离租户替代 MinIO bucket.

    同步 IO (硬链接/复制/扫描/删除) 全部经 ``asyncio.to_thread`` 包装; 流式上传走 aiofiles.
    """

    def __init__(self, base_path: str | None = None) -> None:
        self._base_path = Path(base_path or settings.MODEL_BASE_PATH)

    def _version_dir(self, tenant_name: str, storage_path: str) -> Path:
        return self._base_path / sanitize_k8s_name(tenant_name) / storage_path

    def _resolve_within(self, version_dir: Path, name: str) -> Path:
        """解析 ``name`` 相对 ``version_dir`` 的绝对路径, 校验未逃逸 (防 ``../`` 穿越).

        ``name`` 允许含子目录 (如 ``sub/model.bin``), 但解析后必须等于或在 version_dir 内.
        """
        base = version_dir.resolve()
        target = (base / name).resolve()
        if target != base and base not in target.parents:
            raise ValueError(f"非法路径: {name}")
        return target

    async def ensure_version_dir(self, tenant_name: str, storage_path: str) -> Path:
        version_dir = self._version_dir(tenant_name, storage_path)
        await self._mkdir(version_dir)
        return version_dir

    async def save_upload_stream(
        self, tenant_name: str, storage_path: str, filename: str, upload_file: UploadFile
    ) -> int:
        """流式分块落盘一个上传文件, 返回写入字节数. 路径 B (本地上传) 使用."""
        version_dir = self._version_dir(tenant_name, storage_path)
        target = self._resolve_within(version_dir, filename)
        await self._mkdir(target.parent)

        written = 0
        async with aiofiles.open(target, "wb") as out:
            while True:
                chunk = await upload_file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                await out.write(chunk)
                written += len(chunk)
        return written

    async def link_or_copy_model_sources(
        self,
        tenant_name: str,
        storage_path: str,
        sources: list[str],
        home_root: str,
        workspace_root: str,
    ) -> tuple[int, int]:
        """把用户指定的模型源文件/目录硬链接 (失败回退复制) 到版本目录.

        每个 source 必须为 canonical 容器路径:
          * ``/kubeai/home/<self-user>/<rel>``
          * ``/kubeai/workspace/<self-tenant>/<rel>``
        ``<self-user>`` = ``sanitize_k8s_name(Path(home_root).name)``,
        ``<self-tenant>`` = ``sanitize_k8s_name(Path(workspace_root).name)``.
        身份首段必须等于自身 sanitize 结果, 防跨用户 / 跨租户访问;
        ``Path.resolve()`` 阻断 ``..`` 与符号链接逃逸.

        注册前预校验: 源存在性 + 目标去重; 任一失败整体回滚, 不留半截版本目录;
        保留相对层级到版本目录 (含目录递归 os.walk).
        返回 (file_count, total_size_bytes).
        """
        version_dir = await self.ensure_version_dir(tenant_name, storage_path)
        home = Path(home_root).resolve()
        workspace = Path(workspace_root).resolve()
        self_user = sanitize_k8s_name(home.name)
        self_tenant = sanitize_k8s_name(workspace.parent.name)

        def _resolve_source(raw: str) -> tuple[Path, str]:
            """(源绝对路径, 版本目录内相对层级). 非法路径抛 ``ValueError``."""
            s = raw.strip()
            if s.startswith(f"{HOME_PREFIX}/"):
                root, prefix_label, identity = home, HOME_PREFIX, self_user
            elif s.startswith(f"{WORKSPACE_PREFIX}/"):
                root, prefix_label, identity = workspace, WORKSPACE_PREFIX, self_tenant
            else:
                raise ValueError(f"仅支持访问 {HOME_PREFIX} 与 {WORKSPACE_PREFIX} 目录: {raw}")
            # canonical 必须含身份首段: /kubeai/home/<self-user>/<rel>
            if not s.startswith(f"{prefix_label}/{identity}/"):
                raise ValueError(f"路径必须含身份首段 {prefix_label}/{identity}/<rel>: {raw}")
            rel = s[len(f"{prefix_label}/{identity}/") :]
            src = (root / rel).resolve()
            if src != root and root not in src.parents:
                raise ValueError(f"非法路径 (逃逸允许目录): {raw}")
            return src, rel

        def _do() -> tuple[int, int]:
            # Pass 1: 解析 + 存在性预校验 + 目标去重. 任一失败整体回滚, 不留半截版本目录.
            plan: list[tuple[Path, Path]] = []
            seen: set[Path] = set()
            for raw in sources:
                src, rel = _resolve_source(raw)
                if not src.exists():
                    raise FileNotFoundError(f"文件不存在: {raw}")
                dst = self._resolve_within(version_dir, rel)
                if dst in seen:
                    raise ValueError(f"路径冲突, 多个源映射到同一目标: {rel}")
                seen.add(dst)
                plan.append((src, dst))

            # Pass 2: 硬链接/复制, 保留相对层级.
            file_count = 0
            total_size = 0
            for src, dst in plan:
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    self._link_or_copy_file(src, dst)
                    file_count += 1
                    total_size += src.stat().st_size
                elif src.is_dir():
                    for root, _dirs, files in os.walk(src):
                        rel_root = Path(root).relative_to(src)
                        (dst / rel_root).mkdir(parents=True, exist_ok=True)
                        for fn in files:
                            s = Path(root) / fn
                            d = dst / rel_root / fn
                            self._link_or_copy_file(s, d)
                            file_count += 1
                            total_size += s.stat().st_size
            return file_count, total_size

        return await asyncio.to_thread(_do)

    async def list_files(self, tenant_name: str, storage_path: str) -> list[dict[str, Any]]:
        """递归列出版本目录下所有文件, file_name 为相对版本根的 posix 路径.

        与原 MinIO ``list_objects`` 返回结构对齐: file_name/size_bytes/content_type/last_modified
        (last_modified 为 UTC datetime).
        """
        version_dir = self._version_dir(tenant_name, storage_path)

        def _list() -> list[dict[str, Any]]:
            if not version_dir.exists():
                return []
            results: list[dict[str, Any]] = []
            for p in sorted(version_dir.rglob("*")):
                if p.is_file():
                    rel = p.relative_to(version_dir)
                    stat = p.stat()
                    results.append(
                        {
                            "file_name": rel.as_posix(),
                            "size_bytes": stat.st_size,
                            "content_type": self._guess_content_type(p.name),
                            "last_modified": datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                        }
                    )
            return results

        return await asyncio.to_thread(_list)

    def resolve_file_path(self, tenant_name: str, storage_path: str, file_name: str) -> Path:
        """解析下载文件绝对路径 (含穿越校验). 供下载端点 FileResponse 使用."""
        return self._resolve_within(self._version_dir(tenant_name, storage_path), file_name)

    async def delete_version(self, tenant_name: str, storage_path: str) -> None:
        """递归删除版本目录 (ignore_errors, 失败不抛)."""
        await self._rmtree(self._version_dir(tenant_name, storage_path))

    @staticmethod
    def _link_or_copy_file(src: Path, dst: Path) -> None:
        """同盘硬链接优先, EXDEV/已存在/不支持时回退 copy2."""
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy2(src, dst)

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


_model_storage: ModelStorage | None = None


def get_model_storage() -> ModelStorage:
    """ModelStorage 模块级单例 (无状态无连接)."""
    global _model_storage
    if _model_storage is None:
        _model_storage = ModelStorage()
    return _model_storage
