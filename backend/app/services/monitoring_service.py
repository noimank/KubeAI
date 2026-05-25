from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.integrations.k8s.resource_quota import (
    _parse_cpu as parse_cpu,
)
from app.integrations.k8s.resource_quota import (
    _parse_memory as parse_memory,
)
from app.integrations.k8s.resource_quota import (
    get_all_tenants_usage,
    get_cluster_capacity,
    get_cluster_usage,
    get_node_resource_details,
)
from app.models.enums import InferenceServiceStatus, TenantStatus, TrainingJobStatus
from app.models.inference_service import InferenceService
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class MonitoringService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_cluster_overview(self) -> dict[str, Any]:
        try:
            capacity = await get_cluster_capacity()
            usage = await get_cluster_usage()
        except Exception:
            logger.exception("k8s_cluster_overview_failed")
            return _empty_overview()

        total_gpu = int(capacity.get("gpu", "0"))
        total_cpu = parse_cpu(capacity.get("cpu", "0"))
        total_memory = parse_memory(capacity.get("memory", "0"))

        used_gpu = int(usage.get("gpu", "0"))
        used_cpu = parse_cpu(usage.get("cpu", "0"))
        used_memory = parse_memory(usage.get("memory", "0"))
        used_storage = parse_memory(usage.get("storage", "0"))

        return {
            "gpu": {"total": total_gpu, "used": used_gpu, "utilization": _pct(used_gpu, total_gpu)},
            "cpu": {"total": total_cpu, "used": used_cpu, "utilization": _pct(used_cpu, total_cpu)},
            "memory": {"total": total_memory, "used": used_memory, "utilization": _pct(used_memory, total_memory)},
            "storage": {"used": used_storage},
        }

    async def get_node_details(self) -> list[dict[str, Any]]:
        try:
            return await get_node_resource_details()
        except Exception:
            logger.exception("k8s_node_details_failed")
            return []

    async def get_tenant_resource_summary(self) -> list[dict[str, Any]]:
        tenants_result = await self.db.execute(select(Tenant).where(Tenant.status == TenantStatus.ACTIVE))
        tenants = tenants_result.scalars().all()

        try:
            ns_usage_list = await get_all_tenants_usage()
        except Exception:
            logger.exception("k8s_tenants_usage_failed")
            ns_usage_list = []

        ns_map: dict[str, dict[str, Any]] = {item["namespace"]: item for item in ns_usage_list}

        summaries: list[dict[str, Any]] = []
        for tenant in tenants:
            ns_name = tenant.k8s_namespace_name
            ns_data = ns_map.get(ns_name, {}) if ns_name else {}

            quota = ns_data.get("quota", {})
            used = ns_data.get("used", {})

            active_jobs_count = await self._count_active_jobs(tenant.id)
            running_services_count = await self._count_running_services(tenant.id)

            summaries.append(
                {
                    "tenant_id": str(tenant.id),
                    "tenant_name": tenant.display_name or tenant.name,
                    "namespace": ns_name,
                    "gpu": {
                        "used": used.get("gpu", 0) if isinstance(used.get("gpu"), int) else 0,
                        "quota": quota.get("gpu", tenant.gpu_limit)
                        if isinstance(quota.get("gpu", int | None), int)
                        else tenant.gpu_limit,
                    },
                    "cpu": {"used": used.get("cpu", "0"), "quota": quota.get("cpu", tenant.cpu_limit)},
                    "memory": {"used": used.get("memory", "0"), "quota": quota.get("memory", tenant.memory_limit)},
                    "storage": {"used": used.get("storage", "0"), "quota": quota.get("storage", tenant.storage_limit)},
                    "active_jobs_count": active_jobs_count,
                    "running_services_count": running_services_count,
                }
            )

        return summaries

    async def get_tenant_resource_detail(self, tenant_id: uuid.UUID) -> dict[str, Any] | None:
        result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
        tenant = result.scalar_one_or_none()
        if not tenant:
            return None

        ns_name = tenant.k8s_namespace_name
        ns_data: dict[str, Any] = {}
        if ns_name:
            try:
                ns_usage_list = await get_all_tenants_usage()
                ns_map = {item["namespace"]: item for item in ns_usage_list}
                ns_data = ns_map.get(ns_name, {})
            except Exception:
                logger.exception("k8s_tenant_detail_failed")

        quota = ns_data.get("quota", {})
        used = ns_data.get("used", {})

        active_jobs = await self._get_active_jobs(tenant_id)
        running_services = await self._get_running_services(tenant_id)

        return {
            "tenant_id": str(tenant.id),
            "tenant_name": tenant.display_name or tenant.name,
            "namespace": ns_name,
            "gpu": {
                "used": used.get("gpu", 0) if isinstance(used.get("gpu"), int) else 0,
                "quota": quota.get("gpu", tenant.gpu_limit)
                if isinstance(quota.get("gpu", int | None), int)
                else tenant.gpu_limit,
            },
            "cpu": {"used": used.get("cpu", "0"), "quota": quota.get("cpu", tenant.cpu_limit)},
            "memory": {"used": used.get("memory", "0"), "quota": quota.get("memory", tenant.memory_limit)},
            "storage": {"used": used.get("storage", "0"), "quota": quota.get("storage", tenant.storage_limit)},
            "active_jobs": active_jobs,
            "running_services": running_services,
        }

    async def _count_active_jobs(self, tenant_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(TrainingJob)
            .where(
                TrainingJob.tenant_id == tenant_id,
                TrainingJob.status.in_(
                    [
                        TrainingJobStatus.RUNNING,
                        TrainingJobStatus.PENDING,
                        TrainingJobStatus.QUEUED,
                        TrainingJobStatus.INITIALIZING,
                    ]
                ),
            )
        )
        return result.scalar() or 0

    async def _count_running_services(self, tenant_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count())
            .select_from(InferenceService)
            .where(
                InferenceService.tenant_id == tenant_id,
                InferenceService.status == InferenceServiceStatus.RUNNING,
            )
        )
        return result.scalar() or 0

    async def _get_active_jobs(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(TrainingJob)
            .where(
                TrainingJob.tenant_id == tenant_id,
                TrainingJob.status.in_(
                    [
                        TrainingJobStatus.RUNNING,
                        TrainingJobStatus.PENDING,
                        TrainingJobStatus.QUEUED,
                        TrainingJobStatus.INITIALIZING,
                    ]
                ),
            )
            .order_by(TrainingJob.created_at.desc())
            .limit(20)
        )
        jobs = result.scalars().all()
        return [{"id": str(j.id), "name": j.name, "status": j.status, "gpu_count": j.gpu_count} for j in jobs]

    async def _get_running_services(self, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(InferenceService)
            .where(
                InferenceService.tenant_id == tenant_id,
                InferenceService.status == InferenceServiceStatus.RUNNING,
            )
            .order_by(InferenceService.created_at.desc())
            .limit(20)
        )
        services = result.scalars().all()
        return [{"id": str(s.id), "name": s.name, "status": s.status, "gpu_count": s.gpu_count} for s in services]


def _pct(used: float, total: float) -> float:
    return round(used / total * 100, 1) if total > 0 else 0.0


def _empty_overview() -> dict[str, Any]:
    return {
        "gpu": {"total": 0, "used": 0, "utilization": 0.0},
        "cpu": {"total": 0, "used": 0, "utilization": 0.0},
        "memory": {"total": 0, "used": 0, "utilization": 0.0},
        "storage": {"used": 0},
    }


async def push_cluster_metrics() -> None:
    """Background task: publish cluster resource metrics via WebSocket."""
    from app.core.ws_pubsub import get_ws_pubsub

    pubsub = get_ws_pubsub()
    if pubsub is None:
        return

    from app.core.database import async_session_factory

    async with async_session_factory() as db:
        try:
            service = MonitoringService(db)
            overview = await service.get_cluster_overview()
            tenants = await service.get_tenant_resource_summary()

            # Publish to each active tenant
            from sqlalchemy import select as sa_select

            result = await db.execute(sa_select(Tenant.id).where(Tenant.status == TenantStatus.ACTIVE))
            for row in result.scalars().all():
                await pubsub.publish(
                    tenant_id=row,
                    event="cluster_resource.metrics_updated",
                    payload={"overview": overview, "tenants_count": len(tenants)},
                )
        except Exception:
            logger.exception("push_cluster_metrics_failed")
