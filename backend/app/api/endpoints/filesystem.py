"""受限文件系统浏览 API — 仅暴露当前用户 home 与当前租户 workspace.

供前端"目录树勾选注册模型"等场景使用; 其它绝对路径一律 403.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException, NotFoundException
from app.integrations.storage.filesystem_browser import (
    MAX_ENTRIES_PER_DIR,
    FilesystemBrowserSecurity,
)
from app.models.tenant import Tenant
from app.schemas.base import BaseResponse

router = APIRouter(prefix="/filesystem", tags=["filesystem"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


class FsBrowseEntry:
    """仅用于文档 — 实际响应是裸 dict, 由 BaseResponse 包裹."""


@router.get("/browse", response_model=BaseResponse[dict[str, object]])
async def browse_filesystem(
    path: Annotated[str, Query(description="容器内路径: /kubeai/home/<user> 或 /kubeai/workspace/<tenant>")],
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
    db: DbDep,
) -> BaseResponse[dict[str, object]]:
    """浏览受限文件系统. 仅返回当前用户的 home 与当前租户的 workspace 根下 1 层目录项.

    越权 (其他用户/租户 / ``..`` 逃逸 / 前缀不符) → 403.
    目录为空或不存在 → 200 + 空 ``entries`` (与 ``ls`` 行为一致).
    """
    if user.tenant_id is None:
        raise ForbiddenException("请先加入租户")
    tenant_row = await db.get(Tenant, user.tenant_id)
    if tenant_row is None:
        raise NotFoundException("租户不存在")

    sec = FilesystemBrowserSecurity(username=user.username, tenant_name=tenant_row.name)
    try:
        # 解析路径, 仅做越权校验 (不强制要求存在 — 与 ls 一致).
        _host_dir, canonical = sec.resolve_container_path(path)
    except PermissionError as e:
        raise ForbiddenException(str(e)) from e
    except ValueError as e:
        raise NotFoundException(str(e)) from e

    # canonical 路径形如 /kubeai/home/<user> 或 /kubeai/workspace/<tenant>, 包含身份首段,
    # 与 list_children 的迭代语义对齐 — entry.path 会继续以 canonical 作为前缀拼接.
    entries, truncated = sec.list_children(canonical)
    return BaseResponse[dict[str, object]](
        data={
            "path": canonical,
            "entries": entries,
            "truncated": truncated or len(entries) >= MAX_ENTRIES_PER_DIR,
        }
    )
