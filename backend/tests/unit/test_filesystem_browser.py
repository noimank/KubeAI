"""FilesystemBrowserSecurity 单测 — 越权 / 列表 / symlink / dotfile / 上限."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from app.integrations.k8s import pvc
from app.integrations.storage.filesystem_browser import (
    HOME_PREFIX,
    MAX_ENTRIES_PER_DIR,
    WORKSPACE_PREFIX,
    FilesystemBrowserSecurity,
)

if TYPE_CHECKING:
    import pytest as _pytest


@pytest.fixture
def data_root(tmp_path: Path, monkeypatch: _pytest.MonkeyPatch) -> Path:
    """把 KUBEAI_DATA_DIR 整体指向 tmp_path, 避免污染真实磁盘."""
    monkeypatch.setattr(pvc, "KUBEAI_DATA_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def fs(data_root: Path) -> FilesystemBrowserSecurity:
    """标准 fixture: alice 用户的 home 与 acme 租户的 workspace 已在 data_root 下."""
    home = data_root / "users" / "alice"
    workspace = data_root / "tenant" / "acme" / "workspace"
    home.mkdir(parents=True)
    workspace.mkdir(parents=True)
    return FilesystemBrowserSecurity(username="alice", tenant_name="acme")


def _create_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def test_self_home_allowed(fs: FilesystemBrowserSecurity) -> None:
    host, canonical = fs.resolve_container_path(f"{HOME_PREFIX}/alice/mycode")
    assert host.name == "mycode"
    assert canonical == f"{HOME_PREFIX}/alice/mycode"


def test_self_home_root_canonical(fs: FilesystemBrowserSecurity) -> None:
    host, canonical = fs.resolve_container_path(HOME_PREFIX)
    assert host.name == "alice"
    # canonical 场景下应自动补齐 self identity, 与 link_or_copy_model_sources 入参格式一致.
    assert canonical == f"{HOME_PREFIX}/alice"


def test_other_user_home_denied(fs: FilesystemBrowserSecurity) -> None:
    with pytest.raises(PermissionError):
        fs.resolve_container_path(f"{HOME_PREFIX}/bob")


def test_other_tenant_workspace_denied(fs: FilesystemBrowserSecurity) -> None:
    with pytest.raises(PermissionError):
        fs.resolve_container_path(f"{WORKSPACE_PREFIX}/other-tenant")


def test_dotdot_escape_denied(fs: FilesystemBrowserSecurity) -> None:
    with pytest.raises(PermissionError):
        fs.resolve_container_path(f"{HOME_PREFIX}/alice/../../etc")


def test_unsupported_prefix_denied(fs: FilesystemBrowserSecurity) -> None:
    with pytest.raises(PermissionError):
        fs.resolve_container_path("/etc/passwd")


def test_root_only_path_rejected(fs: FilesystemBrowserSecurity) -> None:
    with pytest.raises(ValueError):
        fs.resolve_container_path("/")


def test_list_self_home(fs: FilesystemBrowserSecurity, data_root: Path) -> None:
    home_root = data_root / "users" / "alice"
    _create_dir(home_root / "exp-1")
    (home_root / "exp-1" / "model.pth").write_bytes(b"x" * 10)
    (home_root / "README.md").write_bytes(b"hello")

    entries, truncated = fs.list_children(HOME_PREFIX)
    assert truncated is False
    assert {e["name"] for e in entries} == {"exp-1", "README.md"}
    file_entry = next(e for e in entries if e["name"] == "README.md")
    assert file_entry["type"] == "file"
    assert file_entry["size_bytes"] == 5
    dir_entry = next(e for e in entries if e["name"] == "exp-1")
    assert dir_entry["type"] == "directory"
    assert dir_entry["size_bytes"] is None
    # canonical 路径含 self identity (与 link_or_copy_model_sources 入参格式一致)
    assert dir_entry["path"] == f"{HOME_PREFIX}/alice/exp-1"


def test_list_workspace_only_self_tenant(fs: FilesystemBrowserSecurity, data_root: Path) -> None:
    ws_self = data_root / "tenant" / "acme" / "workspace"
    ws_other = data_root / "tenant" / "other" / "workspace"
    _create_dir(ws_self / "exp-1")
    (ws_self / "exp-1" / "model.bin").write_bytes(b"x")
    _create_dir(ws_other / "secret")
    (ws_other / "secret" / "leak.txt").write_bytes(b"x")

    # 列自身 workspace 下的目录项 (与跨租户 workspace 同列)
    entries_top, _ = fs.list_children(WORKSPACE_PREFIX)
    assert {e["name"] for e in entries_top} == {"exp-1"}

    # 进入下一层不暴露其他租户 workspace 的内容
    entries_sub, _ = fs.list_children(f"{WORKSPACE_PREFIX}/acme/exp-1")
    assert {e["name"] for e in entries_sub} == {"model.bin"}


def test_hidden_dotfiles_excluded(fs: FilesystemBrowserSecurity, data_root: Path) -> None:
    home = data_root / "users" / "alice"
    (home / "visible.txt").write_bytes(b"x")
    (home / ".env").write_bytes(b"x")

    entries, _ = fs.list_children(HOME_PREFIX)
    names = {e["name"] for e in entries}
    assert names == {"visible.txt"}


@pytest.mark.skipif(sys.platform == "win32", reason="symlink 需要 SeCreateSymbolicLink 特权, Windows 默认无")
def test_symlink_listed_but_not_directory(fs: FilesystemBrowserSecurity, data_root: Path) -> None:
    home = data_root / "users" / "alice"
    target = data_root / "secret.txt"
    target.write_bytes(b"x")
    (home / "link.txt").symlink_to(target)
    (home / "real_dir").mkdir()
    (home / "real_dir" / "inner.bin").write_bytes(b"y")

    entries, _ = fs.list_children(HOME_PREFIX)
    by_name = {e["name"]: e for e in entries}
    # symlink 出现但不算 directory (前端不可下钻)
    assert by_name["link.txt"]["type"] == "file"
    assert by_name["link.txt"]["size_bytes"] is not None
    assert by_name["real_dir"]["type"] == "directory"


def test_max_entries_cap(fs: FilesystemBrowserSecurity, data_root: Path) -> None:
    home = data_root / "users" / "alice"
    for i in range(MAX_ENTRIES_PER_DIR + 5):
        (home / f"f{i:04d}.txt").write_bytes(b"x")

    entries, truncated = fs.list_children(HOME_PREFIX)
    assert len(entries) == MAX_ENTRIES_PER_DIR
    assert truncated is True


def test_directory_ordering(fs: FilesystemBrowserSecurity, data_root: Path) -> None:
    home = data_root / "users" / "alice"
    (home / "zeta.txt").write_bytes(b"x")
    (home / "alpha").mkdir()
    (home / "beta").mkdir()

    entries, _ = fs.list_children(HOME_PREFIX)
    names = [e["name"] for e in entries]
    # 目录优先 (alpha/beta), 然后文件 (zeta.txt)
    assert names == ["alpha", "beta", "zeta.txt"]


def test_nonexistent_dir_returns_empty(fs: FilesystemBrowserSecurity, data_root: Path) -> None:
    entries, truncated = fs.list_children(f"{HOME_PREFIX}/alice/missing")
    assert entries == []
    assert truncated is False
