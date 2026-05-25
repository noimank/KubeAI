import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import NotFoundException
from app.schemas.base import BaseResponse
from app.schemas.monitoring import (
    CleanupPVCRequest,
    CleanupResult,
    ClusterOverviewResponse,
    NodeResourceDetail,
    OrphanPVCInfo,
    QuotaAllocationOverview,
    QuotaTransferRequest,
    StaleJobInfo,
    TenantQuotaComparison,
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


@router.get("/quota-allocation", response_model=BaseResponse[QuotaAllocationOverview])
async def get_quota_allocation(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "manage"))],
) -> BaseResponse[QuotaAllocationOverview]:
    service = MonitoringService(db)
    data = await service.get_quota_allocation_overview()
    return BaseResponse(data=QuotaAllocationOverview(**data))


@router.get("/quota-comparison", response_model=BaseResponse[list[TenantQuotaComparison]])
async def get_quota_comparison(
    db: Annotated[AsyncSession, Depends(get_db)],
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "manage"))],
) -> BaseResponse[list[TenantQuotaComparison]]:
    service = MonitoringService(db)
    data = await service.get_tenant_quota_comparison()
    items = [TenantQuotaComparison(**t) for t in data]
    return BaseResponse(data=items)


@router.post("/quota-transfer", response_model=BaseResponse[None])
async def transfer_quota(
    req: QuotaTransferRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_permission("monitoring", "manage"))],
) -> BaseResponse[None]:
    service = MonitoringService(db)
    audit_context = {
        "user_id": user.id,
        "ip_address": "",
    }
    await service.transfer_quota(req, audit_context)
    return BaseResponse(message="配额调配成功")


@router.get("/cleanup/stale-jobs", response_model=BaseResponse[list[StaleJobInfo]])
async def get_stale_jobs(
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "manage"))],
) -> BaseResponse[list[StaleJobInfo]]:
    from app.services.resource_cleaner import ResourceCleaner

    cleaner = ResourceCleaner()
    stale_jobs = await cleaner.detect_stale_jobs()
    items = [
        StaleJobInfo(
            id=str(j.id),
            name=j.name,
            tenant_name=j.tenant_name,
            namespace=j.namespace,
            vcjob_name=j.vcjob_name,
            status=j.status,
            finished_at=j.finished_at.isoformat() if j.finished_at else None,
            days_ago=j.days_ago,
        )
        for j in stale_jobs
    ]
    return BaseResponse(data=items)


@router.get("/cleanup/orphan-pvcs", response_model=BaseResponse[list[OrphanPVCInfo]])
async def get_orphan_pvcs(
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "manage"))],
) -> BaseResponse[list[OrphanPVCInfo]]:
    from app.services.resource_cleaner import ResourceCleaner

    cleaner = ResourceCleaner()
    orphans = await cleaner.detect_orphan_pvcs()
    items = [
        OrphanPVCInfo(
            name=o.name,
            namespace=o.namespace,
            storage=o.storage,
            created_at=o.created_at,
            orphan_reason=o.orphan_reason,
        )
        for o in orphans
    ]
    return BaseResponse(data=items)


@router.post("/cleanup/pvcs", response_model=BaseResponse[CleanupResult])
async def cleanup_pvcs(
    req: CleanupPVCRequest,
    user: Annotated[CurrentUser, Depends(require_permission("monitoring", "manage"))],
) -> BaseResponse[CleanupResult]:
    from app.schemas.monitoring import CleanupDetail as CleanupDetailSchema
    from app.services.resource_cleaner import ResourceCleaner

    cleaner = ResourceCleaner()
    audit_context = {"user_id": user.id, "ip_address": ""}
    results = await cleaner.cleanup_pvcs(req.items, audit_context)
    cleaned_count = sum(1 for r in results if r.success)
    failed_count = len(results) - cleaned_count
    details = [
        CleanupDetailSchema(namespace=r.namespace, pvc_name=r.pvc_name, success=r.success, error=r.error)
        for r in results
    ]
    return BaseResponse(data=CleanupResult(cleaned_count=cleaned_count, failed_count=failed_count, details=details))


@router.post("/cleanup/trigger", response_model=BaseResponse[None])
async def trigger_cleanup(
    _user: Annotated[CurrentUser, Depends(require_permission("monitoring", "manage"))],
) -> BaseResponse[None]:
    from app.core.events import get_resource_cleaner

    cleaner = get_resource_cleaner()
    if cleaner:
        await cleaner.trigger_manual_cleanup()
        return BaseResponse(message="清理任务已触发")
    return BaseResponse(success=False, message="清理服务未启用")
