"""ModelStorage 源路径解析与注册前预校验单测.

覆盖 ``link_or_copy_model_sources``: 绝对路径 (/kubeai/home|workspace) 与相对路径
(向后兼容工作空间)、目录递归、文件不存在预校验 (整体回滚不留半截版本目录)、
允许根外绝对路径拒绝、``..`` 逃逸防护、home/workspace 同名目标冲突.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.integrations.storage.model_storage import ModelStorage

if TYPE_CHECKING:
    from pathlib import Path

_TENANT = "acme"
_STORAGE_PATH = "models/my-model/v1"


def _setup_roots(tmp_path: Path) -> tuple[Path, Path, ModelStorage]:
    """构造 home/workspace 根 + ModelStorage (base 指向 tmp), 返回 (home, workspace, storage)."""
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    home.mkdir()
    workspace.mkdir()
    storage = ModelStorage(base_path=str(tmp_path / "models-store"))
    return home, workspace, storage


def _version_dir(tmp_path: Path) -> Path:
    return tmp_path / "models-store" / _TENANT / _STORAGE_PATH


async def test_absolute_home_and_workspace_paths_link_into_version_dir(tmp_path: Path) -> None:
    """绝对路径分别解析到 home/workspace 根, 保留相对层级; 含目录递归分支."""
    home, workspace, storage = _setup_roots(tmp_path)
    (home / "mycode").mkdir()
    (home / "mycode" / "model.pth").write_bytes(b"home-model")
    (workspace / "exp-1").mkdir()
    (workspace / "exp-1" / "config.yaml").write_bytes(b"config")
    (workspace / "exp-1" / "nested").mkdir()
    (workspace / "exp-1" / "nested" / "weights.bin").write_bytes(b"weights")

    file_count, total_size = await storage.link_or_copy_model_sources(
        _TENANT,
        _STORAGE_PATH,
        ["/kubeai/home/mycode/model.pth", "/kubeai/workspace/exp-1"],
        str(home),
        str(workspace),
    )

    vdir = _version_dir(tmp_path)
    assert file_count == 3
    assert total_size == len(b"home-model") + len(b"config") + len(b"weights")
    assert (vdir / "mycode" / "model.pth").read_bytes() == b"home-model"
    assert (vdir / "exp-1" / "config.yaml").read_bytes() == b"config"
    assert (vdir / "exp-1" / "nested" / "weights.bin").read_bytes() == b"weights"


async def test_relative_path_resolves_against_workspace(tmp_path: Path) -> None:
    """不以 / 开头的相对路径按 workspace 解析 (向后兼容旧用法)."""
    _, workspace, storage = _setup_roots(tmp_path)
    (workspace / "exp-1").mkdir()
    (workspace / "exp-1" / "model.pth").write_bytes(b"ws-model")

    file_count, _ = await storage.link_or_copy_model_sources(
        _TENANT, _STORAGE_PATH, ["exp-1/model.pth"], str(tmp_path / "home"), str(workspace)
    )

    assert file_count == 1
    assert (_version_dir(tmp_path) / "exp-1" / "model.pth").read_bytes() == b"ws-model"


async def test_missing_source_aborts_before_any_link(tmp_path: Path) -> None:
    """任一源不存在立即整体失败, 先存在的源也不应被链接 (不留半截版本目录)."""
    _, workspace, storage = _setup_roots(tmp_path)
    (workspace / "exists.pth").write_bytes(b"ok")

    with pytest.raises(FileNotFoundError, match="文件不存在"):
        await storage.link_or_copy_model_sources(
            _TENANT,
            _STORAGE_PATH,
            ["exists.pth", "/kubeai/workspace/missing.pth"],
            str(tmp_path / "home"),
            str(workspace),
        )

    assert not (_version_dir(tmp_path) / "exists.pth").exists()


async def test_absolute_path_outside_allowed_roots_rejected(tmp_path: Path) -> None:
    """允许根之外的绝对路径一律拒绝, 且不触碰真实文件系统."""
    _, _, storage = _setup_roots(tmp_path)

    with pytest.raises(ValueError, match="仅支持访问"):
        await storage.link_or_copy_model_sources(
            _TENANT, _STORAGE_PATH, ["/etc/passwd"], str(tmp_path / "home"), str(tmp_path / "workspace")
        )


async def test_traversal_escape_rejected(tmp_path: Path) -> None:
    """``..`` 解析后逃出允许根 → 拒绝 (不依赖文件是否存在)."""
    home, workspace, storage = _setup_roots(tmp_path)
    (tmp_path / "secret.txt").write_bytes(b"secret")  # home 的同级文件

    with pytest.raises(ValueError, match="逃逸允许目录"):
        await storage.link_or_copy_model_sources(
            _TENANT, _STORAGE_PATH, ["/kubeai/home/../secret.txt"], str(home), str(workspace)
        )


async def test_home_and_workspace_same_relative_target_collide(tmp_path: Path) -> None:
    """home 与 workspace 下同名相对路径映射到同一版本目录目标 → 冲突报错."""
    home, workspace, storage = _setup_roots(tmp_path)
    (home / "model.pth").write_bytes(b"from-home")
    (workspace / "model.pth").write_bytes(b"from-workspace")

    with pytest.raises(ValueError, match="路径冲突"):
        await storage.link_or_copy_model_sources(
            _TENANT,
            _STORAGE_PATH,
            ["/kubeai/home/model.pth", "/kubeai/workspace/model.pth"],
            str(home),
            str(workspace),
        )
