"""ModelStorage 源路径解析与注册前预校验单测.

新架构: ``link_or_copy_model_sources`` 严格只接受 canonical 路径
(``/kubeai/home/<self-user>/<rel>`` 与 ``/kubeai/workspace/<self-tenant>/<rel>``),
身份首段必须等于自身 sanitize 结果. 不再支持旧 textarea 的无身份段形式
或相对路径 — 一律拒绝, 错误前置. 覆盖: 解析、目录递归、文件不存在预校验
(整体回滚不留半截版本目录)、允许根外绝对路径拒绝、``..`` 逃逸防护、
home/workspace 同名目标冲突.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from app.integrations.storage.model_storage import ModelStorage

if TYPE_CHECKING:
    from pathlib import Path

_TENANT = "acme"
_STORAGE_PATH = "models/my-model/v1"
_SELF_USER = "alice"  # = Path(home).name
_SELF_TENANT = "acme"  # = Path(workspace).name


def _setup_roots(tmp_path: Path) -> tuple[Path, Path, ModelStorage]:
    """构造 home/workspace 根 + ModelStorage (base 指向 tmp), 返回 (home, workspace, storage).

    workspace 根必须是 ``<tenant>/workspace`` 嵌套两层 — ``self_tenant`` 从 ``workspace.parent.name`` 派生,
    与 ``make_workspace_host_path`` 的 ``/data/kubeai/tenant/<tenant>/workspace`` 布局一致."""
    home = tmp_path / _SELF_USER
    workspace = tmp_path / _SELF_TENANT / "workspace"
    home.mkdir()
    workspace.mkdir(parents=True)
    storage = ModelStorage(base_path=str(tmp_path / "models-store"))
    return home, workspace, storage


def _version_dir(tmp_path: Path) -> Path:
    return tmp_path / "models-store" / _TENANT / _STORAGE_PATH


async def test_canonical_paths_link_into_version_dir(tmp_path: Path) -> None:
    """canonical 路径分别解析到 home/workspace 根下的 <user>/<rel> 与 <tenant>/<rel>."""
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
        [
            f"/kubeai/home/{_SELF_USER}/mycode/model.pth",
            f"/kubeai/workspace/{_SELF_TENANT}/exp-1",
        ],
        str(home),
        str(workspace),
    )

    vdir = _version_dir(tmp_path)
    assert file_count == 3
    assert total_size == len(b"home-model") + len(b"config") + len(b"weights")
    assert (vdir / "mycode" / "model.pth").read_bytes() == b"home-model"
    assert (vdir / "exp-1" / "config.yaml").read_bytes() == b"config"
    assert (vdir / "exp-1" / "nested" / "weights.bin").read_bytes() == b"weights"


async def test_canonical_directory_recursion(tmp_path: Path) -> None:
    """canonical 路径中目录节点会 os.walk 整 walk (目录级勾选)."""
    home, workspace, storage = _setup_roots(tmp_path)
    (home / "src").mkdir()
    (home / "src" / "a.txt").write_bytes(b"a")
    (home / "src" / "sub").mkdir()
    (home / "src" / "sub" / "b.txt").write_bytes(b"b")

    file_count, _ = await storage.link_or_copy_model_sources(
        _TENANT,
        _STORAGE_PATH,
        [f"/kubeai/home/{_SELF_USER}/src"],
        str(home),
        str(workspace),
    )
    vdir = _version_dir(tmp_path)
    assert file_count == 2
    assert (vdir / "src" / "a.txt").read_bytes() == b"a"
    assert (vdir / "src" / "sub" / "b.txt").read_bytes() == b"b"


async def test_path_without_identity_segment_rejected(tmp_path: Path) -> None:
    """缺身份首段 (如旧 textarea ``/kubeai/home/exp-1``) 一律拒绝."""
    home, workspace, storage = _setup_roots(tmp_path)
    (home / "exp-1" / "model.pth").parent.mkdir(parents=True)
    (home / "exp-1" / "model.pth").write_bytes(b"x")

    with pytest.raises(ValueError, match="身份首段"):
        await storage.link_or_copy_model_sources(
            _TENANT, _STORAGE_PATH, ["/kubeai/home/exp-1"], str(home), str(workspace)
        )


async def test_relative_path_no_longer_supported(tmp_path: Path) -> None:
    """不再支持相对路径 — 全部按 ``仅支持访问 ... 目录`` 拒绝."""
    _, workspace, storage = _setup_roots(tmp_path)
    with pytest.raises(ValueError, match="仅支持访问"):
        await storage.link_or_copy_model_sources(
            _TENANT, _STORAGE_PATH, ["exp-1/model.pth"], str(tmp_path / "x"), str(workspace)
        )


async def test_missing_source_aborts_before_any_link(tmp_path: Path) -> None:
    """任一源不存在立即整体失败, 已存在的源也不应被链接."""
    _, workspace, storage = _setup_roots(tmp_path)
    (workspace / "exists.pth").write_bytes(b"ok")

    with pytest.raises(FileNotFoundError, match="文件不存在"):
        await storage.link_or_copy_model_sources(
            _TENANT,
            _STORAGE_PATH,
            [f"/kubeai/workspace/{_SELF_TENANT}/exists.pth", f"/kubeai/workspace/{_SELF_TENANT}/missing.pth"],
            str(tmp_path / _SELF_USER),
            str(workspace),
        )

    assert not (_version_dir(tmp_path) / "exists.pth").exists()


async def test_absolute_path_outside_allowed_roots_rejected(tmp_path: Path) -> None:
    """其他绝对路径 (如 /etc) 一律拒绝, 不触碰真实文件系统."""
    _, _, storage = _setup_roots(tmp_path)
    with pytest.raises(ValueError, match="仅支持访问"):
        await storage.link_or_copy_model_sources(
            _TENANT, _STORAGE_PATH, ["/etc/passwd"], str(tmp_path / _SELF_USER), str(tmp_path / _SELF_TENANT)
        )


async def test_traversal_escape_rejected(tmp_path: Path) -> None:
    """canonical 内含 ``..`` 时 → 拒绝 (不依赖文件是否存在)."""
    home, workspace, storage = _setup_roots(tmp_path)
    (tmp_path / "secret.txt").write_bytes(b"secret")

    with pytest.raises(ValueError, match="逃逸允许目录"):
        await storage.link_or_copy_model_sources(
            _TENANT,
            _STORAGE_PATH,
            [f"/kubeai/home/{_SELF_USER}/../secret.txt"],
            str(home),
            str(workspace),
        )


async def test_root_only_path_rejected(tmp_path: Path) -> None:
    """``/kubeai/home/<user>`` 缺 <rel> — 已无下钻目标, 拒绝."""
    home, workspace, storage = _setup_roots(tmp_path)
    with pytest.raises(ValueError, match="身份首段"):
        await storage.link_or_copy_model_sources(
            _TENANT,
            _STORAGE_PATH,
            [f"/kubeai/home/{_SELF_USER}"],
            str(home),
            str(workspace),
        )


async def test_home_and_workspace_same_relative_target_collide(tmp_path: Path) -> None:
    """home 与 workspace 下同 <rel> 映射到同一版本目录目标 → 冲突."""
    home, workspace, storage = _setup_roots(tmp_path)
    (home / "model.pth").write_bytes(b"from-home")
    (workspace / "model.pth").write_bytes(b"from-workspace")

    with pytest.raises(ValueError, match="路径冲突"):
        await storage.link_or_copy_model_sources(
            _TENANT,
            _STORAGE_PATH,
            [f"/kubeai/home/{_SELF_USER}/model.pth", f"/kubeai/workspace/{_SELF_TENANT}/model.pth"],
            str(home),
            str(workspace),
        )


async def test_other_user_home_rejected(tmp_path: Path) -> None:
    """他人 home 即便写入身份段也仍然不匹配 — 路径身份不再等于 sanitize(username)."""
    home, workspace, storage = _setup_roots(tmp_path)
    with pytest.raises(ValueError, match="身份首段"):
        await storage.link_or_copy_model_sources(
            _TENANT, _STORAGE_PATH, ["/kubeai/home/bob/x"], str(home), str(workspace)
        )


async def test_other_tenant_workspace_rejected(tmp_path: Path) -> None:
    _, workspace, storage = _setup_roots(tmp_path)
    with pytest.raises(ValueError, match="身份首段"):
        await storage.link_or_copy_model_sources(
            _TENANT, _STORAGE_PATH, ["/kubeai/workspace/other/x"], str(tmp_path / _SELF_USER), str(workspace)
        )
