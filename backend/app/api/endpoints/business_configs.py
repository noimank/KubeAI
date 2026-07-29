"""业务配置管理 API。"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.business_config import BusinessConfigCreate, BusinessConfigResponse, BusinessConfigUpdate
from app.services.business_config_service import BusinessConfigService

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _require_tenant(tenant_id: uuid.UUID | None) -> uuid.UUID:
    if tenant_id is None:
        raise ForbiddenException("请先加入租户")
    return tenant_id


router = APIRouter(prefix="/business-configs", tags=["business-configs"])


@router.post("", response_model=BaseResponse[BusinessConfigResponse])
async def create_config(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("business_configs", "write"))],
    data: BusinessConfigCreate,
) -> BaseResponse[BusinessConfigResponse]:
    """创建业务配置。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = BusinessConfigService(db)
    result = await svc.create(tenant_id, user.id, data)
    return BaseResponse(data=BusinessConfigResponse(**result), message="创建成功")


@router.get("", response_model=PageResponse[BusinessConfigResponse])
async def list_configs(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("business_configs", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
) -> PageResponse[BusinessConfigResponse]:
    """分页列出业务配置。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = BusinessConfigService(db)
    items, total = await svc.list_configs(tenant_id, page, page_size, search)
    return PageResponse(
        data=PageData(
            items=[BusinessConfigResponse(**item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        ),
        message="查询成功",
    )


@router.get("/{config_id}", response_model=BaseResponse[BusinessConfigResponse])
async def get_config(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("business_configs", "read"))],
    config_id: uuid.UUID,
) -> BaseResponse[BusinessConfigResponse]:
    """获取单个业务配置。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = BusinessConfigService(db)
    result = await svc.get(tenant_id, config_id)
    return BaseResponse(data=BusinessConfigResponse(**result), message="查询成功")


@router.put("/{config_id}", response_model=BaseResponse[BusinessConfigResponse])
async def update_config(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("business_configs", "write"))],
    config_id: uuid.UUID,
    data: BusinessConfigUpdate,
) -> BaseResponse[BusinessConfigResponse]:
    """更新业务配置。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = BusinessConfigService(db)
    result = await svc.update(tenant_id, config_id, data)
    return BaseResponse(data=BusinessConfigResponse(**result), message="更新成功")


@router.delete("/{config_id}", response_model=BaseResponse[None])
async def delete_config(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("business_configs", "manage"))],
    config_id: uuid.UUID,
) -> BaseResponse[None]:
    """删除业务配置。"""
    tenant_id = _require_tenant(user.tenant_id)
    svc = BusinessConfigService(db)
    await svc.delete(tenant_id, config_id)
    return BaseResponse(data=None, message="配置已删除")
