from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

if TYPE_CHECKING:
    import uuid

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
)
from app.models.annotation import AnnotationProject
from app.models.annotation_task import AnnotationTask
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import (
    AnnotationTaskStatus,
    TenantStatus,
    TrainingJobStatus,
)
from app.models.inference_service import InferenceService
from app.models.notification import Notification
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_engineer_dashboard(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
        resource_overview = await self._get_resource_overview(tenant_id)
        recent_jobs = await self._get_recent_training_jobs(tenant_id, limit=5)
        recent_datasets = await self._get_recent_datasets(tenant_id, limit=5)

        return {
            "role": "engineer",
            "data": {
                "resource_overview": resource_overview,
                "recent_training_jobs": recent_jobs,
                "recent_datasets": recent_datasets,
            },
        }

    async def get_admin_dashboard(self, user_id: uuid.UUID) -> dict[str, Any]:
        cluster_overview = await self._get_cluster_overview_brief()
        tenant_ranking = await self._get_tenant_ranking()
        recent_alerts = await self._get_recent_alerts(user_id, limit=10)

        return {
            "role": "admin",
            "data": {
                "cluster_overview": cluster_overview,
                "tenant_ranking": tenant_ranking,
                "recent_alerts": recent_alerts,
            },
        }

    async def get_annotator_dashboard(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
        progress_overview = await self._get_annotation_progress(user_id, tenant_id)
        pending_tasks = await self._get_pending_annotation_projects(user_id, tenant_id)

        return {
            "role": "annotator",
            "data": {
                "progress_overview": progress_overview,
                "pending_tasks": pending_tasks,
            },
        }

    async def get_mlops_dashboard(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
        resource_overview = await self._get_resource_overview(tenant_id)
        recent_services = await self._get_recent_inference_services(tenant_id, limit=5)

        return {
            "role": "mlops",
            "data": {
                "resource_overview": resource_overview,
                "recent_inference_services": recent_services,
            },
        }

    async def _get_resource_overview(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        gpu_used = 0
        gpu_total = 0
        try:
            tenant_result = await self.db.execute(select(Tenant).where(Tenant.id == tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            if tenant:
                gpu_total = tenant.gpu_limit
                if tenant.k8s_namespace_name:
                    from app.integrations.k8s.resource_quota import get_quota_used

                    used = await get_quota_used(tenant.k8s_namespace_name)
                    gpu_used = int(used.get("requests.nvidia.com/gpu", "0"))
        except Exception:
            logger.exception("dashboard_resource_overview_failed")

        active_jobs = await self._count_active_jobs(tenant_id)
        active_datasets_result = await self.db.execute(
            select(func.count()).select_from(Dataset).where(Dataset.tenant_id == tenant_id)
        )
        active_datasets = active_datasets_result.scalar() or 0

        return {
            "gpu_used": gpu_used,
            "gpu_total": gpu_total,
            "active_jobs": active_jobs,
            "active_datasets": active_datasets,
        }

    async def _get_recent_training_jobs(self, tenant_id: uuid.UUID, limit: int = 5) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(TrainingJob)
            .where(TrainingJob.tenant_id == tenant_id)
            .order_by(TrainingJob.created_at.desc())
            .limit(limit)
        )
        jobs = result.scalars().all()
        return [
            {
                "id": str(j.id),
                "name": j.name,
                "status": j.status,
                "gpu_count": j.gpu_count,
                "created_at": j.created_at,
            }
            for j in jobs
        ]

    async def _get_recent_datasets(self, tenant_id: uuid.UUID, limit: int = 5) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Dataset).where(Dataset.tenant_id == tenant_id).order_by(Dataset.created_at.desc()).limit(limit)
        )
        datasets = result.scalars().all()

        items = []
        for ds in datasets:
            version_count_result = await self.db.execute(
                select(func.count()).select_from(DatasetVersion).where(DatasetVersion.dataset_id == ds.id)
            )
            version_count = version_count_result.scalar() or 0

            latest_version = await self.db.execute(
                select(DatasetVersion)
                .where(DatasetVersion.dataset_id == ds.id)
                .order_by(DatasetVersion.created_at.desc())
                .limit(1)
            )
            latest = latest_version.scalar_one_or_none()

            items.append(
                {
                    "id": str(ds.id),
                    "name": ds.name,
                    "display_name": ds.display_name,
                    "version_count": version_count,
                    "file_count": latest.file_count if latest else 0,
                    "updated_at": latest.created_at if latest else ds.created_at,
                }
            )
        return items

    async def _get_cluster_overview_brief(self) -> dict[str, Any]:
        try:
            capacity = await get_cluster_capacity()
            usage = await get_cluster_usage()
        except Exception:
            logger.exception("dashboard_cluster_overview_failed")
            return {
                "gpu_total": 0,
                "gpu_used": 0,
                "gpu_utilization": 0.0,
                "cpu_total": 0,
                "cpu_used": 0,
                "cpu_utilization": 0.0,
                "memory_total": 0,
                "memory_used": 0,
                "memory_utilization": 0.0,
            }

        gpu_total = int(capacity.get("gpu", "0"))
        gpu_used = int(usage.get("gpu", "0"))
        cpu_total = parse_cpu(capacity.get("cpu", "0"))
        cpu_used = parse_cpu(usage.get("cpu", "0"))
        mem_total = parse_memory(capacity.get("memory", "0"))
        mem_used = parse_memory(usage.get("memory", "0"))

        return {
            "gpu_total": gpu_total,
            "gpu_used": gpu_used,
            "gpu_utilization": _pct(gpu_used, gpu_total),
            "cpu_total": cpu_total,
            "cpu_used": cpu_used,
            "cpu_utilization": _pct(cpu_used, cpu_total),
            "memory_total": mem_total,
            "memory_used": mem_used,
            "memory_utilization": _pct(mem_used, mem_total),
        }

    async def _get_tenant_ranking(self) -> list[dict[str, Any]]:
        tenants_result = await self.db.execute(select(Tenant).where(Tenant.status == TenantStatus.ACTIVE))
        tenants = tenants_result.scalars().all()

        try:
            ns_usage_list = await get_all_tenants_usage()
        except Exception:
            logger.exception("dashboard_tenant_ranking_failed")
            ns_usage_list = []
        ns_map: dict[str, dict[str, Any]] = {item["namespace"]: item for item in ns_usage_list}

        ranking = []
        for tenant in tenants:
            ns_name = tenant.k8s_namespace_name
            ns_data = ns_map.get(ns_name, {}) if ns_name else {}
            used = ns_data.get("used", {})

            gpu_used = int(used.get("gpu", 0)) if isinstance(used.get("gpu"), (int, float)) else 0
            cpu_used = parse_cpu(str(used.get("cpu", "0")))
            cpu_quota = parse_cpu(tenant.cpu_limit)

            active_jobs = await self._count_active_jobs(tenant.id)

            ranking.append(
                {
                    "tenant_id": str(tenant.id),
                    "tenant_name": tenant.display_name or tenant.name,
                    "gpu_quota": tenant.gpu_limit,
                    "gpu_used": gpu_used,
                    "gpu_utilization": _pct(gpu_used, tenant.gpu_limit),
                    "cpu_utilization": _pct(cpu_used, cpu_quota),
                    "active_jobs": active_jobs,
                }
            )

        ranking.sort(key=lambda x: x["gpu_utilization"], reverse=True)  # type: ignore[arg-type,return-value]
        return ranking

    async def _get_recent_alerts(self, user_id: uuid.UUID, limit: int = 10) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        alerts = result.scalars().all()
        return [
            {
                "id": str(n.id),
                "type": n.type.value if n.type else "",
                "title": n.title,
                "priority": n.priority.value if n.priority else "medium",
                "created_at": n.created_at,
            }
            for n in alerts
        ]

    async def _get_annotation_progress(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
        pending_count_result = await self.db.execute(
            select(func.count())
            .select_from(AnnotationTask)
            .where(
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
                AnnotationTask.status.in_([AnnotationTaskStatus.ASSIGNED, AnnotationTaskStatus.IN_PROGRESS]),
            )
        )
        pending_count = pending_count_result.scalar() or 0

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        today_completed_result = await self.db.execute(
            select(func.count())
            .select_from(AnnotationTask)
            .where(
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
                AnnotationTask.status == AnnotationTaskStatus.COMPLETED,
                AnnotationTask.updated_at >= today_start,
            )
        )
        today_completed = today_completed_result.scalar() or 0

        total_assigned_result = await self.db.execute(
            select(func.count())
            .select_from(AnnotationTask)
            .where(
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
            )
        )
        total_assigned = total_assigned_result.scalar() or 0

        total_completed_result = await self.db.execute(
            select(func.count())
            .select_from(AnnotationTask)
            .where(
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
                AnnotationTask.status == AnnotationTaskStatus.COMPLETED,
            )
        )
        total_completed = total_completed_result.scalar() or 0

        completion_rate = _pct(total_completed, total_assigned)

        return {
            "pending_count": pending_count,
            "today_completed": today_completed,
            "total_completion_rate": completion_rate,
        }

    async def _get_pending_annotation_projects(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(AnnotationProject)
            .where(
                AnnotationProject.tenant_id == tenant_id,
                AnnotationProject.status.in_(["active", "draft"]),
            )
            .order_by(AnnotationProject.created_at.desc())
        )
        projects = result.scalars().all()

        items = []
        for project in projects:
            user_task_result = await self.db.execute(
                select(func.count())
                .select_from(AnnotationTask)
                .where(
                    AnnotationTask.project_id == project.id,
                    AnnotationTask.assigned_to == user_id,
                    AnnotationTask.status.in_([AnnotationTaskStatus.ASSIGNED, AnnotationTaskStatus.IN_PROGRESS]),
                )
            )
            user_pending = user_task_result.scalar() or 0
            if user_pending == 0 and project.status != "active":
                continue

            items.append(
                {
                    "id": str(project.id),
                    "project_id": str(project.id),
                    "project_name": project.name,
                    "status": project.status,
                    "total_tasks": project.total_tasks,
                    "completed_tasks": project.completed_tasks,
                }
            )
        return items

    async def _get_recent_inference_services(self, tenant_id: uuid.UUID, limit: int = 5) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(InferenceService)
            .where(InferenceService.tenant_id == tenant_id)
            .order_by(InferenceService.created_at.desc())
            .limit(limit)
        )
        services = result.scalars().all()
        return [
            {
                "id": str(s.id),
                "name": s.name,
                "status": s.status,
                "replicas": s.replicas,
                "endpoint_url": s.proxy_endpoint or s.endpoint_url,
            }
            for s in services
        ]

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


def _pct(used: float, total: float) -> float:
    return round(used / total * 100, 1) if total > 0 else 0.0
