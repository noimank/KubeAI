import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import NotFoundException
from app.schemas.base import BaseResponse
from app.schemas.monitoring import (
    ClusterOverviewResponse,
    NodeResourceDetail,
    TenantResourceDetail,
    TenantResourceSummary,
)
from app.services.monitoring_service import MonitoringService

router = APIRouter(prefix="/monitoring", tags=["monitoring"])


@router.get("/cluster-overview", response_model=BaseResponse[ClusterOverviewResponse])
async def get_cluster_overview(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "read"))],
) -> BaseResponse[ClusterOverviewResponse]:
    service = MonitoringService(db)
    data = await service.get_cluster_overview()
    return BaseResponse(data=ClusterOverviewResponse(**data))


@router.get("/nodes", response_model=BaseResponse[list[NodeResourceDetail]])
async def get_node_details(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "read"))],
) -> BaseResponse[list[NodeResourceDetail]]:
    service = MonitoringService(db)
    data = await service.get_node_details()
    nodes = [NodeResourceDetail(**node) for node in data]
    return BaseResponse(data=nodes)


@router.get("/tenants", response_model=BaseResponse[list[TenantResourceSummary]])
async def get_tenant_resource_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "read"))],
) -> BaseResponse[list[TenantResourceSummary]]:
    service = MonitoringService(db)
    data = await service.get_tenant_resource_summary()
    tenants = [TenantResourceSummary(**t) for t in data]
    return BaseResponse(data=tenants)


@router.get("/tenants/{tenant_id}", response_model=BaseResponse[TenantResourceDetail])
async def get_tenant_resource_detail(
    tenant_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "read"))],
) -> BaseResponse[TenantResourceDetail]:
    service = MonitoringService(db)
    data = await service.get_tenant_resource_detail(tenant_id)
    if data is None:
        raise NotFoundException("租户不存在")
    return BaseResponse(data=TenantResourceDetail(**data))
