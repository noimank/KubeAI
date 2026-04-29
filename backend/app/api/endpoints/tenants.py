from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.tenant import TenantCreateRequest, TenantResponse
from app.services.tenant_service import TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("", response_model=BaseResponse[TenantResponse])
async def create_tenant(
    req: TenantCreateRequest,
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
) -> BaseResponse[TenantResponse]:
    service = TenantService(db)
    tenant = await service.create_tenant(req)
    data = TenantResponse(
        id=tenant.id,
        name=tenant.name,
        display_name=tenant.display_name,
        description=tenant.description,
        status=tenant.status,
        k8s_namespace_name=tenant.k8s_namespace_name,
        gpu_limit=tenant.gpu_limit,
        cpu_limit=tenant.cpu_limit,
        memory_limit=tenant.memory_limit,
        storage_limit=tenant.storage_limit,
        created_at=tenant.created_at,
        updated_at=tenant.updated_at,
    )
    return BaseResponse(data=data, message="租户创建成功")


@router.get("", response_model=PageResponse[TenantResponse])
async def list_tenants(
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("tenants", "manage"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[TenantResponse]:
    service = TenantService(db)
    items, total = await service.list_tenants(page=page, page_size=page_size)
    tenant_list = [TenantResponse(**item) for item in items]
    page_data = PageData(items=tenant_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")
