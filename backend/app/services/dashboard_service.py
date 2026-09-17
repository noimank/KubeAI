from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.core.casbin import CasbinEnforcer
from app.models.annotation import AnnotationProject
from app.models.annotation_task import AnnotationTask
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AnnotationTaskStatus
from app.models.inference_service import InferenceService
from app.models.training_job import TrainingJob

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.identity import TokenIdentity

logger = logging.getLogger(__name__)


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_dashboard(self, user: TokenIdentity) -> dict[str, Any]:
        """统一概览: 按权限裁剪的明细分区."""
        role = user.role.value
        tenant_id = user.tenant_id

        recent_training_jobs = None
        recent_datasets = None
        recent_inference_services = None
        pending_annotations = None
        if tenant_id is not None:
            if CasbinEnforcer.enforce(role, "training_jobs", "read"):
                recent_training_jobs = await self._get_recent_training_jobs(tenant_id)
            if CasbinEnforcer.enforce(role, "datasets", "read"):
                recent_datasets = await self._get_recent_datasets(tenant_id)
            if CasbinEnforcer.enforce(role, "inference_services", "read"):
                recent_inference_services = await self._get_recent_inference_services(tenant_id)
            if CasbinEnforcer.enforce(role, "annotations", "read"):
                pending_annotations = await self._get_pending_annotation_projects(user.id, tenant_id)

        return {
            "recent_training_jobs": recent_training_jobs,
            "recent_datasets": recent_datasets,
            "recent_inference_services": recent_inference_services,
            "pending_annotations": pending_annotations,
        }

    async def _get_recent_training_jobs(self, tenant_id: uuid.UUID, limit: int = 5) -> list[dict[str, Any]]:
        result = await self.db.execute(
            # 与训练任务列表口径一致: 超参调优 trial 任务不进最近训练任务
            select(TrainingJob)
            .where(TrainingJob.tenant_id == tenant_id, TrainingJob.source != "tuning")
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
                    "project_id": str(project.id),
                    "project_name": project.name,
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
