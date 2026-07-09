"""受限文件系统浏览器 — 仅允许 /kubeai/home/<user> 与 /kubeai/workspace/<tenant>.

为训练完成注册模型等场景提供"路径即选"体验: 用户在前端目录树里勾选文件或目录,
提交时的 canonical 路径直接复用 :data:`app.integrations.storage.model_storage.HOME_PREFIX` /
:data:`WORKSPACE_PREFIX` — 与注册接口 ``link_or_copy_model_sources`` 的
``_resolve_source`` 校验语义完全一致.

越权策略
--------
- 仅接受 ``/kubeai/home/...`` 或 ``/kubeai/workspace/...`` 前缀, 其它一律拒绝 (转 403).
- ``Path.resolve()`` 后必须等于或仍在对应 root 之内, 防 ``..`` 与符号链接逃逸.
- 列表阶段仅当 entry 不是 symlink 且 ``lstat().st_mode`` 指示目录才可下钻, 避免前端
  钻取到任意 host 路径.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.pvc import (
    make_user_home_host_path,
    make_workspace_host_path,
)
from app.integrations.storage.model_storage import (
    HOME_PREFIX,
    WORKSPACE_PREFIX,
)

# 单层 listdir 上限 — 防止 1w+ 文件的虚拟目录拖慢请求 / OOM.
MAX_ENTRIES_PER_DIR = 500
# dotfile 前缀 — 与 Unix ``ls`` 习惯一致, 默认隐藏.
HIDDEN_PREFIX = "."


class FsEntryDict(TypedDict):
    """单条目录项的响应字段. 前端 ``FileBrowser`` 组件直接消费."""

    name: str
    path: str  # canonical 容器内路径, 与 file_paths 入参兼容
    type: str  # "directory" | "file"
    size_bytes: int | None


@dataclass(frozen=True)
class AllowedRoots:
    home: Path  # /data/kubeai/users/<sanitized username>
    workspace: Path  # /data/kubeai/tenant/<sanitized tenant>/workspace


class FilesystemBrowserSecurity:
    """封装越权校验 + 单层目录列表的纯函数式 API, 便于独立单测."""

    def __init__(self, username: str, tenant_name: str) -> None:
        self._username = username
        self._tenant_name = tenant_name
        # 与 make_user_home_host_path 内部的 sanitize 规则完全一致 — 路径合法性由前缀层校验,
        # 此处 self_user/self_tenant 仅用于"比较用户身份与路径身份是否相同".
        self._self_user = sanitize_k8s_name(username)
        self._self_tenant = sanitize_k8s_name(tenant_name)
        self._roots = AllowedRoots(
            home=Path(make_user_home_host_path(username)).resolve(),
            workspace=Path(make_workspace_host_path(tenant_name)).resolve(),
        )

    @property
    def allowed_roots(self) -> tuple[Path, Path]:
        return self._roots.home, self._roots.workspace

    def resolve_container_path(self, container_path: str) -> tuple[Path, str]:
        """输入容器内路径, 返回 (host 绝对路径, canonical 容器路径).

        canonical 路径形式:
          - 根: ``/kubeai/home`` 或 ``/kubeai/workspace`` (不含 ``/`` 结尾)
          - 子目录/文件: ``/kubeai/home/<rel>`` 或 ``/kubeai/workspace/<rel>``

        越权 (``..`` / 前缀不符 / 逃逸) 抛 ``PermissionError``;
        路径格式错误抛 ``ValueError``.
        """
        s = (container_path or "").strip()
        if not s or s == "/":
            raise ValueError("请指定 /kubeai/home/<用户名> 或 /kubeai/workspace/<租户名> 路径")
        if s == HOME_PREFIX or s.startswith(f"{HOME_PREFIX}/"):
            prefix = HOME_PREFIX
            root = self._roots.home
            rel = s[len(prefix) + 1 :] if s.startswith(f"{HOME_PREFIX}/") else ""
        elif s == WORKSPACE_PREFIX or s.startswith(f"{WORKSPACE_PREFIX}/"):
            prefix = WORKSPACE_PREFIX
            root = self._roots.workspace
            rel = s[len(prefix) + 1 :] if s.startswith(f"{WORKSPACE_PREFIX}/") else ""
        else:
            raise PermissionError(f"仅允许浏览 {HOME_PREFIX}/<用户名> 与 {WORKSPACE_PREFIX}/<租户名> 路径")
        # 用户/租户身份强校验: /kubeai/home/<user> 第一段必须等于自身 sanitize 结果.
        if rel:
            head = rel.split("/", 1)[0]
            expected = self._self_user if prefix == HOME_PREFIX else self._self_tenant
            if head != expected:
                raise PermissionError(
                    f"仅能访问{'自己的 home 目录' if prefix == HOME_PREFIX else '当前租户的工作空间'}: "
                    f"{prefix}/{expected}"
                )
            # rel 形如 <user>/<...>, 从 host 角度看 user 段恰好是 root 自身, 故去掉该前缀.
            sub_rel = rel[len(expected) + 1 :] if rel != expected else ""
            if sub_rel:
                target = (root / sub_rel).resolve()
                if target != root and root not in target.parents:
                    raise PermissionError(f"路径超出允许目录: {container_path}")
            else:
                target = root
        else:
            # root 列表: host 直接 = root, canonical 后续由 list_children 自行拼.
            target = root
            expected = self._self_user if prefix == HOME_PREFIX else self._self_tenant
        canonical = s if s != prefix else f"{prefix}/{expected}"
        return target, canonical

    def list_children(self, container_path: str) -> tuple[list[FsEntryDict], bool]:
        """listdir 单层, 应用隐藏/排序/上限. 返回 (entries, truncated).

        canonical 路径规则: 列表场景下保证 entry.path 含 self identity 前缀 —
        list_children("/kubeai/home") -> entries[i]["path"] 形如 /kubeai/home/alice/<name>,
        与 ``link_or_copy_model_sources`` 的 ``_resolve_source`` 入参路径规则一致.
        """
        host_dir, canonical = self.resolve_container_path(container_path)
        try:
            if not host_dir.is_dir():
                return [], False
        except OSError:
            return [], False

        try:
            raw = list(host_dir.iterdir())
        except (PermissionError, OSError):
            return [], False
        entries = [p for p in raw if not p.name.startswith(HIDDEN_PREFIX)]
        # 目录优先, 同类内按名称字典序.
        entries.sort(key=lambda p: (not (p.is_dir() and not p.is_symlink()), p.name.lower()))
        truncated = len(entries) > MAX_ENTRIES_PER_DIR
        if truncated:
            entries = entries[:MAX_ENTRIES_PER_DIR]

        items: list[FsEntryDict] = []
        for p in entries:
            try:
                st = p.lstat()
            except OSError:
                continue
            # symlink 不视为可下钻目录 — 防止跨租户逃逸.
            is_dir = p.is_dir() and not p.is_symlink()
            items.append(
                FsEntryDict(
                    name=p.name,
                    path=f"{canonical.rstrip('/')}/{p.name}",
                    type="directory" if is_dir else "file",
                    size_bytes=st.st_size if not is_dir and p.is_file() else None,
                )
            )
        return items, truncated
