from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.core.exceptions import BadRequestException, NotFoundException, QuotaExceededException
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
    get_quota_used,
    update_resource_quota,
)
from app.models.enums import AuditAction, InferenceServiceStatus, ResourceType, TenantStatus, TrainingJobStatus
from app.models.inference_service import InferenceService
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.monitoring import QuotaTransferRequest

logger = logging.getLogger(__name__)


class MonitoringService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_quota_allocation_overview(self) -> dict[str, Any]:
        capacity = await get_cluster_capacity()
        total_gpu = int(capacity.get("gpu", "0"))
        total_cpu = parse_cpu(capacity.get("cpu", "0"))
        total_memory = parse_memory(capacity.get("memory", "0"))

        result = await self.db.execute(select(Tenant).where(Tenant.status == TenantStatus.ACTIVE))
        tenants = result.scalars().all()

        allocated_gpu = sum(t.gpu_limit for t in tenants)
        allocated_cpu = sum(parse_cpu(t.cpu_limit) for t in tenants)
        allocated_memory = sum(parse_memory(t.memory_limit) for t in tenants)

        return {
            "gpu": {
                "total": total_gpu,
                "allocated": allocated_gpu,
                "available": max(total_gpu - allocated_gpu, 0),
            },
            "cpu": {
                "total": total_cpu,
                "allocated": allocated_cpu,
                "available": max(total_cpu - allocated_cpu, 0),
            },
            "memory": {
                "total": total_memory,
                "allocated": allocated_memory,
                "available": max(total_memory - allocated_memory, 0),
            },
        }

    async def get_tenant_quota_comparison(self) -> list[dict[str, Any]]:
        tenants_result = await self.db.execute(select(Tenant).where(Tenant.status == TenantStatus.ACTIVE))
        tenants = tenants_result.scalars().all()

        try:
            ns_usage_list = await get_all_tenants_usage()
        except Exception:
            logger.exception("k8s_tenants_usage_failed")
            ns_usage_list = []

        ns_map: dict[str, dict[str, Any]] = {item["namespace"]: item for item in ns_usage_list}

        comparisons: list[dict[str, Any]] = []
        for tenant in tenants:
            ns_name = tenant.k8s_namespace_name
            ns_data = ns_map.get(ns_name, {}) if ns_name else {}
            used = ns_data.get("used", {})

            gpu_quota = tenant.gpu_limit
            gpu_used = int(used.get("gpu", 0)) if isinstance(used.get("gpu"), (int, float)) else 0
            cpu_quota = parse_cpu(tenant.cpu_limit)
            cpu_used = parse_cpu(str(used.get("cpu", "0")))
            mem_quota = parse_memory(tenant.memory_limit)
            mem_used = parse_memory(str(used.get("memory", "0")))
            stor_quota = parse_memory(tenant.storage_limit)
            stor_used = parse_memory(str(used.get("storage", "0")))

            comparisons.append(
                {
                    "tenant_id": str(tenant.id),
                    "tenant_name": tenant.display_name or tenant.name,
                    "gpu": {
                        "quota": gpu_quota,
                        "used": gpu_used,
                        "utilization": _pct(gpu_used, gpu_quota),
                    },
                    "cpu": {
                        "quota": cpu_quota,
                        "used": cpu_used,
                        "utilization": _pct(cpu_used, cpu_quota),
                    },
                    "memory": {
                        "quota": mem_quota,
                        "used": mem_used,
                        "utilization": _pct(mem_used, mem_quota),
                    },
                    "storage": {
                        "quota": stor_quota,
                        "used": stor_used,
                        "utilization": _pct(stor_used, stor_quota),
                    },
                }
            )

        return comparisons

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

    async def transfer_quota(self, req: QuotaTransferRequest, audit_context: dict[str, Any]) -> None:
        """调配配额 — 校验 + DB 写入。K8s ResourceQuota 同步由 Taskiq worker 异步执行."""
        if req.source_tenant_id == req.target_tenant_id:
            raise BadRequestException("源租户和目标租户不能相同")

        source = await self._get_active_tenant(req.source_tenant_id)
        target = await self._get_active_tenant(req.target_tenant_id)

        if not source.k8s_namespace_name or not target.k8s_namespace_name:
            raise BadRequestException("租户尚未完成 K8s 命名空间初始化")

        resource_type = req.resource_type
        amount = self._parse_amount(resource_type, req.amount)

        # Get cluster capacity for overflow checks
        capacity = await get_cluster_capacity()
        cluster_gpu = int(capacity.get("gpu", "0"))
        cluster_cpu = parse_cpu(capacity.get("cpu", "0"))
        cluster_memory = parse_memory(capacity.get("memory", "0"))

        # Calculate total allocated (excluding source tenant for source check, excluding target for target check)
        allocated_result = await self.db.execute(
            select(Tenant).where(
                Tenant.status == TenantStatus.ACTIVE,
                Tenant.id.notin_([source.id]),
            )
        )
        other_tenants = allocated_result.scalars().all()
        other_allocated_gpu = sum(t.gpu_limit for t in other_tenants)
        other_allocated_cpu = sum(parse_cpu(t.cpu_limit) for t in other_tenants)
        other_allocated_memory = sum(parse_memory(t.memory_limit) for t in other_tenants)

        # Check source tenant: new quota must not be below current usage
        source_used = await self._get_tenant_k8s_usage(source.k8s_namespace_name)
        source_new_quota = self._get_tenant_quota_value(source, resource_type) - amount

        if resource_type == "gpu":
            source_current_used = source_used.get("gpu", 0)
        elif resource_type == "cpu":
            source_current_used = parse_cpu(str(source_used.get("cpu", "0")))
        elif resource_type == "memory":
            source_current_used = parse_memory(str(source_used.get("memory", "0")))
        else:
            source_current_used = parse_memory(str(source_used.get("storage", "0")))

        if not req.force and source_current_used > source_new_quota:
            raise QuotaExceededException("调出方使用量将超过新配额")

        # Check target tenant: new quota must not exceed cluster available
        target_new_quota = self._get_tenant_quota_value(target, resource_type) + amount

        if resource_type == "gpu":
            if other_allocated_gpu + target_new_quota > cluster_gpu:
                raise QuotaExceededException("超过集群可分配资源")
        elif resource_type == "cpu":
            if other_allocated_cpu + target_new_quota > cluster_cpu:
                raise QuotaExceededException("超过集群可分配资源")
        elif resource_type == "memory" and other_allocated_memory + target_new_quota > cluster_memory:
            raise QuotaExceededException("超过集群可分配资源")

        # Apply quota changes to DB
        self._set_tenant_quota_value(source, resource_type, source_new_quota)
        self._set_tenant_quota_value(target, resource_type, target_new_quota)
        await self.db.flush()

        # Audit log
        audit_svc = AuditService(self.db)
        await audit_svc.log_action(
            action=AuditAction.TRANSFER_QUOTA,
            resource_type=ResourceType.QUOTA,
            resource_id=str(source.id),
            detail={
                "source_tenant_id": str(source.id),
                "source_tenant_name": source.display_name or source.name,
                "target_tenant_id": str(target.id),
                "target_tenant_name": target.display_name or target.name,
                "resource_type": resource_type,
                "amount": req.amount,
            },
            tenant_id=source.id,
            **audit_context,
        )

    async def execute_quota_transfer(self, req: QuotaTransferRequest) -> None:
        """由 Taskiq worker 调用: 同步 K8s ResourceQuota (仅写操作)."""
        source = await self._get_active_tenant(req.source_tenant_id)
        target = await self._get_active_tenant(req.target_tenant_id)

        for tenant in [source, target]:
            try:
                await update_resource_quota(
                    namespace=tenant.k8s_namespace_name,  # type: ignore[arg-type]
                    gpu_limit=tenant.gpu_limit,
                    cpu_limit=tenant.cpu_limit,
                    memory_limit=tenant.memory_limit,
                    storage_limit=tenant.storage_limit,
                )
            except Exception:
                logger.error("K8s ResourceQuota 同步失败: tenant=%s", tenant.id, exc_info=True)

    def _parse_amount(self, resource_type: str, amount: str) -> int | float:
        if resource_type == "gpu":
            return int(amount)
        if resource_type == "cpu":
            return parse_cpu(amount)
        return parse_memory(amount)

    def _get_tenant_quota_value(self, tenant: Tenant, resource_type: str) -> int | float:
        if resource_type == "gpu":
            return tenant.gpu_limit
        if resource_type == "cpu":
            return parse_cpu(tenant.cpu_limit)
        if resource_type == "memory":
            return parse_memory(tenant.memory_limit)
        return parse_memory(tenant.storage_limit)

    def _set_tenant_quota_value(self, tenant: Tenant, resource_type: str, value: int | float) -> None:
        if resource_type == "gpu":
            tenant.gpu_limit = int(value)
        elif resource_type == "cpu":
            tenant.cpu_limit = str(int(value))
        elif resource_type == "memory":
            tenant.memory_limit = self._format_memory(value)
        else:
            tenant.storage_limit = self._format_memory(value)

    def _format_memory(self, ki: int | float) -> str:
        if ki >= 1024**2:
            return f"{int(ki // 1024**2)}Gi"
        if ki >= 1024:
            return f"{int(ki // 1024)}Mi"
        return f"{int(ki)}Ki"

    async def _get_active_tenant(self, tenant_id: uuid.UUID) -> Tenant:
        result = await self.db.execute(
            select(Tenant).where(Tenant.id == tenant_id, Tenant.status == TenantStatus.ACTIVE)
        )
        tenant = result.scalar_one_or_none()
        if not tenant:
            raise NotFoundException("租户不存在或已禁用")
        return tenant

    async def _get_tenant_k8s_usage(self, namespace: str) -> dict[str, Any]:
        try:
            used = await get_quota_used(namespace)
            return {
                "gpu": int(used.get("requests.nvidia.com/gpu", "0")),
                "cpu": used.get("requests.cpu", "0"),
                "memory": used.get("requests.memory", "0"),
                "storage": used.get("requests.storage", "0"),
            }
        except Exception:
            logger.exception("获取 K8s 使用量失败: ns=%s", namespace)
            return {"gpu": 0, "cpu": "0", "memory": "0", "storage": "0"}

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
