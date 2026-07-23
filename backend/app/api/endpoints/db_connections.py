"""数据库连接管理 API。"""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.db_connection import DbConnectionCreate, DbConnectionResponse, DbConnectionUpdate
from app.services.db_connection_service import DbConnectionService

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _require_tenant(tenant_id: uuid.UUID | None) -> uuid.UUID:
    if tenant_id is None:
        raise ForbiddenException("请先加入租户")
    return tenant_id


router = APIRouter(prefix="/db-connections", tags=["db-connections"])


@router.post("", response_model=BaseResponse[DbConnectionResponse])
async def create_connection(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "write"))],
    data: DbConnectionCreate,
) -> BaseResponse[DbConnectionResponse]:
    """创建数据库连接配置。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = DbConnectionService(db)
    result = await svc.create(tenant_id, user.id, data)
    return BaseResponse(data=DbConnectionResponse(**result), message="连接创建成功")


@router.get("", response_model=PageResponse[DbConnectionResponse])
async def list_connections(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
) -> PageResponse[DbConnectionResponse]:
    """分页列出租户的数据库连接。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = DbConnectionService(db)
    items, total = await svc.list_connections(tenant_id, page, page_size, search)
    return PageResponse(
        data=PageData(
            items=[DbConnectionResponse(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
        message="查询成功",
    )


@router.get("/{connection_id}", response_model=BaseResponse[DbConnectionResponse])
async def get_connection(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "read"))],
    connection_id: uuid.UUID,
) -> BaseResponse[DbConnectionResponse]:
    """获取单个数据库连接详情（不含密码）。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = DbConnectionService(db)
    result = await svc.get(tenant_id, connection_id)
    return BaseResponse(data=DbConnectionResponse(**result), message="查询成功")


@router.put("/{connection_id}", response_model=BaseResponse[DbConnectionResponse])
async def update_connection(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "write"))],
    connection_id: uuid.UUID,
    data: DbConnectionUpdate,
) -> BaseResponse[DbConnectionResponse]:
    """更新数据库连接配置。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = DbConnectionService(db)
    result = await svc.update(tenant_id, connection_id, data)
    return BaseResponse(data=DbConnectionResponse(**result), message="连接更新成功")


@router.delete("/{connection_id}", response_model=BaseResponse[None])
async def delete_connection(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "manage"))],
    connection_id: uuid.UUID,
) -> BaseResponse[None]:
    """删除数据库连接配置。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = DbConnectionService(db)
    await svc.delete(tenant_id, connection_id)
    return BaseResponse(data=None, message="连接已删除")


@router.post("/{connection_id}/test", response_model=BaseResponse[dict[str, Any]])
async def test_connection(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("data_explore", "read"))],
    connection_id: uuid.UUID,
) -> BaseResponse[dict[str, Any]]:
    """测试数据库连接连通性。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = DbConnectionService(db)
    result = await svc.test_connection(tenant_id, connection_id)
    return BaseResponse(data=result, message="测试完成")
