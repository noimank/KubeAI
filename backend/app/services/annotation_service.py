from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import ExternalServiceException, NotFoundException
from app.integrations.labelstudio.templates import LABELING_TEMPLATES
from app.models.annotation import AnnotationProject
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AuditAction, ResourceType
from app.models.tenant import Tenant
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.integrations.labelstudio.client import LabelStudioClient
    from app.integrations.minio.client import MinIOClient

logger = logging.getLogger(__name__)


class AnnotationService:
    def __init__(self, db: AsyncSession, labelstudio_client: LabelStudioClient, minio_client: MinIOClient):
        self.db = db
        self.ls_client = labelstudio_client
        self.minio = minio_client

    async def _get_tenant_name(self, tenant_id: uuid.UUID) -> str:
        result = await self.db.execute(select(Tenant.name).where(Tenant.id == tenant_id))
        name = result.scalar_one_or_none()
        if not name:
            raise NotFoundException("租户不存在")
        return name

    async def create_project(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        dataset_id: uuid.UUID,
        dataset_version_id: uuid.UUID,
        annotation_type: str,
        audit_context: dict[str, Any] | None = None,
    ) -> AnnotationProject:
        # Validate dataset and version
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(dataset_version_id, dataset_id)

        # Get template
        template = LABELING_TEMPLATES.get(annotation_type)
        if not template:
            raise NotFoundException(f"标注模板不存在: {annotation_type}")

        label_config = template["config"]

        # Create project in LabelStudio
        try:
            ls_project = await self.ls_client.create_project(name, description or "", label_config)
            ls_project_id = ls_project["id"]
        except Exception as e:
            raise ExternalServiceException(f"创建 LabelStudio 项目失败: {e}") from e

        # Import tasks from dataset version files
        tenant_name = await self._get_tenant_name(tenant_id)
        prefix = f"datasets/{dataset.name}/v{version.version_number}/"
        objects = await self.minio.list_objects(tenant_name, prefix)

        tasks: list[dict[str, Any]] = []
        if annotation_type == "text_classification":
            for obj in objects:
                object_name = obj["object_name"]
                file_name = object_name.removeprefix(prefix)
                url = await self.minio.presigned_get_url(tenant_name, object_name)
                tasks.append({"data": {"text": url, "file_name": file_name}})
        else:
            for obj in objects:
                object_name = obj["object_name"]
                url = await self.minio.presigned_get_url(tenant_name, object_name)
                tasks.append({"data": {"image": url}})

        if tasks:
            try:
                await self.ls_client.import_tasks(ls_project_id, tasks)
            except Exception as e:
                logger.warning("导入 LabelStudio tasks 失败: %s", e)

        # Create DB record
        project = AnnotationProject(
            name=name,
            description=description,
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            annotation_type=annotation_type,
            label_studio_project_id=ls_project_id,
            label_config=label_config,
            total_tasks=len(tasks),
            completed_tasks=0,
            status="active",
            tenant_id=tenant_id,
            created_by=user_id,
        )
        self.db.add(project)
        await self.db.flush()
        await self.db.refresh(project)

        if audit_context:
            await self._log_audit(
                action=AuditAction.CREATE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(project.id),
                detail={"name": name, "annotation_type": annotation_type},
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.commit()
        return project

    async def list_projects(
        self,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
    ) -> tuple[list[AnnotationProject], int]:
        query = (
            select(AnnotationProject)
            .options(selectinload(AnnotationProject.dataset), selectinload(AnnotationProject.dataset_version))
            .where(AnnotationProject.tenant_id == tenant_id)
        )
        if keyword:
            query = query.where(AnnotationProject.name.ilike(f"%{keyword}%"))

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(AnnotationProject.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_project(self, project_id: uuid.UUID, tenant_id: uuid.UUID) -> AnnotationProject:
        result = await self.db.execute(
            select(AnnotationProject)
            .options(selectinload(AnnotationProject.dataset), selectinload(AnnotationProject.dataset_version))
            .where(AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundException("标注项目不存在")

        # Sync stats from LabelStudio
        await self._sync_project_stats(project)

        return project

    async def delete_project(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> None:
        result = await self.db.execute(
            select(AnnotationProject).where(
                AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundException("标注项目不存在")

        # Delete from LabelStudio
        if project.label_studio_project_id is not None:
            try:
                await self.ls_client.delete_project(project.label_studio_project_id)
            except Exception as e:
                logger.warning("删除 LabelStudio 项目失败: %s", e)

        if audit_context:
            await self._log_audit(
                action=AuditAction.DELETE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(project.id),
                detail={"name": project.name},
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.delete(project)
        await self.db.commit()

    async def _sync_project_stats(self, project: AnnotationProject) -> None:
        if project.label_studio_project_id is None:
            return
        try:
            stats = await self.ls_client.get_project_stats(project.label_studio_project_id)
            project.total_tasks = stats.get("total", project.total_tasks)
            project.completed_tasks = stats.get("completed", project.completed_tasks)
            await self.db.flush()
        except Exception as e:
            logger.warning("同步 LabelStudio 统计失败: %s", e)

    async def _get_dataset_or_fail(self, dataset_id: uuid.UUID, tenant_id: uuid.UUID) -> Dataset:
        result = await self.db.execute(select(Dataset).where(Dataset.id == dataset_id, Dataset.tenant_id == tenant_id))
        dataset = result.scalar_one_or_none()
        if not dataset:
            raise NotFoundException("数据集不存在")
        return dataset

    async def _get_version_or_fail(self, version_id: uuid.UUID, dataset_id: uuid.UUID) -> DatasetVersion:
        result = await self.db.execute(
            select(DatasetVersion).where(DatasetVersion.id == version_id, DatasetVersion.dataset_id == dataset_id)
        )
        version = result.scalar_one_or_none()
        if not version:
            raise NotFoundException("数据集版本不存在")
        return version

    async def _log_audit(
        self,
        action: AuditAction,
        resource_type: ResourceType,
        resource_id: str,
        detail: dict[str, Any] | None = None,
        tenant_id: uuid.UUID | None = None,
        **kwargs: Any,
    ) -> None:
        audit_svc = AuditService(self.db)
        await audit_svc.log_action(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            detail=detail,
            tenant_id=tenant_id,
            **kwargs,
        )
