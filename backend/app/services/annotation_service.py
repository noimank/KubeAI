from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import ExternalServiceException, ForbiddenException, NotFoundException
from app.integrations.labelstudio.templates import LABELING_TEMPLATES
from app.models.annotation import AnnotationProject
from app.models.annotation_task import AnnotationTask
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AuditAction, ResourceType
from app.models.tenant import Tenant
from app.models.user import User
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.integrations.labelstudio.client import LabelStudioClient
    from app.integrations.minio.client import MinIOClient
    from app.schemas.annotation import AnnotationBatchAssignRequest, AnnotationTaskAssignRequest

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
            ls_project_id = await self.ls_client.create_project(name, description or "", label_config)
        except ExternalServiceException:
            raise
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
                tasks.append({"data": {"image": url, "object_name": object_name}})

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

        # Import tasks to LabelStudio and create AnnotationTask records
        if tasks:
            try:
                ls_tasks = await self.ls_client.import_tasks(ls_project_id, tasks)
                for ls_task in ls_tasks:
                    self.db.add(
                        AnnotationTask(
                            project_id=project.id,
                            label_studio_task_id=ls_task["id"],
                            data=ls_task["data"],
                            assigned_to=None,
                            status="unassigned",
                            tenant_id=tenant_id,
                        )
                    )
                project.total_tasks = len(ls_tasks)
                await self.db.flush()
            except ExternalServiceException:
                logger.warning("导入 LabelStudio tasks 失败, 项目已创建但 tasks 未导入")
            except Exception as e:
                logger.warning("导入 LabelStudio tasks 失败: %s", e)

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

    async def list_project_tasks(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        assigned_to: uuid.UUID | None = None,
    ) -> tuple[list[AnnotationTask], int]:
        await self._validate_project_membership(project_id, tenant_id)

        query = (
            select(AnnotationTask)
            .options(selectinload(AnnotationTask.project), selectinload(AnnotationTask.assignee))
            .where(
                AnnotationTask.project_id == project_id,
                AnnotationTask.tenant_id == tenant_id,
            )
        )
        if status:
            query = query.where(AnnotationTask.status == status)
        if assigned_to:
            query = query.where(AnnotationTask.assigned_to == assigned_to)

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(AnnotationTask.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def assign_tasks(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        request: AnnotationTaskAssignRequest,
        audit_context: dict[str, Any] | None = None,
    ) -> int:
        await self._validate_project_membership(project_id, tenant_id)
        await self._validate_tenant_membership(request.user_id, tenant_id)

        result = await self.db.execute(
            select(AnnotationTask).where(
                AnnotationTask.id.in_(request.task_ids),
                AnnotationTask.project_id == project_id,
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.status.in_(["unassigned", "assigned"]),
            )
        )
        tasks = list(result.scalars().all())

        if len(tasks) != len(request.task_ids):
            found_ids = {t.id for t in tasks}
            missing = set(request.task_ids) - found_ids
            raise NotFoundException(f"以下任务不存在或不可分配: {missing}")

        for task in tasks:
            task.assigned_to = request.user_id
            task.status = "assigned"

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(project_id),
                detail={
                    "action": "assign_tasks",
                    "task_count": len(tasks),
                    "assigned_to": str(request.user_id),
                },
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.commit()
        return len(tasks)

    async def batch_assign(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        request: AnnotationBatchAssignRequest,
        audit_context: dict[str, Any] | None = None,
    ) -> int:
        await self._validate_project_membership(project_id, tenant_id)
        for uid in request.user_ids:
            await self._validate_tenant_membership(uid, tenant_id)

        result = await self.db.execute(
            select(AnnotationTask)
            .where(
                AnnotationTask.project_id == project_id,
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.status == "unassigned",
            )
            .order_by(AnnotationTask.created_at)
        )
        unassigned_tasks = list(result.scalars().all())

        total_to_assign = min(len(unassigned_tasks), request.tasks_per_user * len(request.user_ids))
        for i in range(total_to_assign):
            user = request.user_ids[i % len(request.user_ids)]
            unassigned_tasks[i].assigned_to = user
            unassigned_tasks[i].status = "assigned"

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(project_id),
                detail={
                    "action": "batch_assign",
                    "assigned_count": total_to_assign,
                    "user_count": len(request.user_ids),
                    "tasks_per_user": request.tasks_per_user,
                },
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.commit()
        return total_to_assign

    async def list_my_tasks(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[AnnotationTask], int]:
        query = (
            select(AnnotationTask)
            .options(selectinload(AnnotationTask.project), selectinload(AnnotationTask.assignee))
            .where(
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
            )
            .order_by(AnnotationTask.created_at.desc())
        )

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(query.offset((page - 1) * page_size).limit(page_size))
        return list(result.scalars().all()), total

    async def get_my_task_summary(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(
                AnnotationTask.project_id,
                AnnotationProject.name.label("project_name"),
                AnnotationProject.annotation_type,
                func.count().label("total_tasks"),
                func.count().filter(AnnotationTask.status == "assigned").label("assigned_tasks"),
                func.count().filter(AnnotationTask.status == "completed").label("completed_tasks"),
            )
            .join(AnnotationProject, AnnotationTask.project_id == AnnotationProject.id)
            .where(
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
            )
            .group_by(AnnotationTask.project_id, AnnotationProject.name, AnnotationProject.annotation_type)
        )
        rows = result.all()
        return [
            {
                "project_id": row.project_id,
                "project_name": row.project_name,
                "annotation_type": row.annotation_type,
                "total_tasks": row.total_tasks,
                "assigned_tasks": row.assigned_tasks,
                "completed_tasks": row.completed_tasks,
            }
            for row in rows
        ]

    async def start_annotation(
        self,
        task_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AnnotationTask:
        task = await self._get_task_with_project(task_id, tenant_id)
        if task.assigned_to != user_id:
            raise ForbiddenException("只能标注分配给自己的任务")
        if task.status == "in_progress":
            return await self._refresh_presigned_url(task)
        if task.status != "assigned":
            raise ForbiddenException("任务状态不是「已分配」，无法开始标注")  # noqa: RUF001
        task.status = "in_progress"
        task = await self._refresh_presigned_url(task)
        await self.db.flush()
        task = await self._reload_task_for_response(task.id, tenant_id)
        await self.db.commit()
        return task

    async def submit_annotation(
        self,
        task_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        result: list[dict[str, Any]],
        audit_context: dict[str, Any] | None = None,
    ) -> AnnotationTask:
        task = await self._get_task_with_project(task_id, tenant_id)
        if task.assigned_to != user_id:
            raise ForbiddenException("只能提交分配给自己的任务")
        if task.status != "in_progress":
            raise ForbiddenException("任务状态不是「进行中」，无法提交")  # noqa: RUF001

        if task.label_studio_task_id:
            await self.ls_client.create_annotation(task.label_studio_task_id, result)

        task.status = "completed"

        project = task.project
        project.completed_tasks = (project.completed_tasks or 0) + 1

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(task.project_id),
                detail={"action": "submit_annotation", "task_id": str(task_id)},
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.flush()
        task = await self._reload_task_for_response(task.id, tenant_id)
        await self.db.commit()
        return task

    async def get_next_task(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AnnotationTask | None:
        await self._validate_project_membership(project_id, tenant_id)
        result = await self.db.execute(
            select(AnnotationTask)
            .options(
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.dataset),
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.dataset_version),
                selectinload(AnnotationTask.assignee),
            )
            .where(
                AnnotationTask.project_id == project_id,
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
                AnnotationTask.status.in_(["in_progress", "assigned"]),
            )
            .order_by(case((AnnotationTask.status == "in_progress", 0), else_=1), AnnotationTask.created_at)
            .limit(1)
        )
        task = result.scalar_one_or_none()
        if task is None:
            return None
        return await self._refresh_presigned_url(task)

    async def get_task_detail(
        self,
        task_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> AnnotationTask:
        task = await self._get_task_with_project(task_id, tenant_id)
        return await self._refresh_presigned_url(task)

    async def _get_task_with_project(self, task_id: uuid.UUID, tenant_id: uuid.UUID) -> AnnotationTask:
        result = await self.db.execute(
            select(AnnotationTask)
            .options(
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.dataset),
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.dataset_version),
                selectinload(AnnotationTask.project),
                selectinload(AnnotationTask.assignee),
            )
            .where(AnnotationTask.id == task_id, AnnotationTask.tenant_id == tenant_id)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise NotFoundException("标注任务不存在")
        return task

    async def _reload_task_for_response(self, task_id: uuid.UUID, tenant_id: uuid.UUID) -> AnnotationTask:
        result = await self.db.execute(
            select(AnnotationTask)
            .options(
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.dataset),
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.dataset_version),
                selectinload(AnnotationTask.assignee),
            )
            .where(AnnotationTask.id == task_id, AnnotationTask.tenant_id == tenant_id)
            .execution_options(populate_existing=True)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise NotFoundException("标注任务不存在")
        return task

    async def _refresh_presigned_url(self, task: AnnotationTask) -> AnnotationTask:
        project = task.project
        if not project or not project.dataset or not project.dataset_version:
            return task

        tenant_name = await self._get_tenant_name(task.tenant_id)
        prefix = f"datasets/{project.dataset.name}/v{project.dataset_version.version_number}/"
        annotation_type = project.annotation_type

        data = dict(task.data)

        if annotation_type == "text_classification":
            file_name = data.get("file_name", "")
            if file_name:
                text_object = f"{prefix}{file_name}"
                data["text"] = await self.minio.presigned_get_url(tenant_name, text_object)
        elif annotation_type in ("image_classification", "object_detection", "image_segmentation"):
            image_object: str | None = data.get("object_name")
            if not image_object:
                image_url = data.get("image", "")
                if image_url and "?" in image_url:
                    path_part = image_url.split("?")[0]
                    image_object = path_part.split("/", 4)[-1] if path_part.count("/") >= 4 else ""
            if image_object:
                data["object_name"] = image_object
                data["image"] = await self.minio.presigned_get_url(tenant_name, image_object)

        task.data = data
        return task

    async def _validate_project_membership(self, project_id: uuid.UUID, tenant_id: uuid.UUID) -> AnnotationProject:
        result = await self.db.execute(
            select(AnnotationProject).where(
                AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id
            )
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundException("标注项目不存在")
        return project

    async def _validate_tenant_membership(self, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        result = await self.db.execute(select(User.tenant_id).where(User.id == user_id))
        user_tenant_id = result.scalar_one_or_none()
        if user_tenant_id != tenant_id:
            raise ForbiddenException("用户不属于当前租户")

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
