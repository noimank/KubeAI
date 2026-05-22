from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from io import BytesIO
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import selectinload

from app.core.exceptions import BadRequestException, ExternalServiceException, ForbiddenException, NotFoundException
from app.integrations.labelstudio.templates import (
    TEXT_OBJECT_TAGS,
    URL_OBJECT_TAGS,
    get_primary_data_object,
    parse_label_config,
)
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
    from app.schemas.annotation import (
        AnnotationBatchAssignRequest,
        AnnotationTaskAssignRequest,
        AnnotationTaskUnassignRequest,
    )

logger = logging.getLogger(__name__)

_MINIO_CONCURRENCY = 20
_LS_BATCH_SIZE = 250


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
        label_config: str,
        audit_context: dict[str, Any] | None = None,
    ) -> AnnotationProject:
        # Validate dataset and version
        dataset = await self._get_dataset_or_fail(dataset_id, tenant_id)
        version = await self._get_version_or_fail(dataset_version_id, dataset_id)

        config_info = parse_label_config(label_config)
        annotation_type = config_info.annotation_type

        # Enumerate MinIO objects
        tenant_name = await self._get_tenant_name(tenant_id)
        prefix = f"datasets/{dataset.name}/v{version.version_number}/"
        objects = await self.minio.list_objects(tenant_name, prefix)
        if not objects:
            raise BadRequestException("数据集版本没有可标注文件")

        # Prepare task data with concurrent MinIO operations
        tasks = await self._prepare_task_data(objects, prefix, config_info, tenant_name)

        # Create project in LabelStudio
        try:
            ls_project_id = await self.ls_client.create_project(name, description or "", label_config)
        except ExternalServiceException:
            raise
        except Exception as e:
            raise ExternalServiceException(f"创建 LabelStudio 项目失败: {e}") from e

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

        # Import tasks to LabelStudio and create DB records
        if tasks:
            try:
                ls_tasks = await self._import_tasks_batched(ls_project_id, tasks)
                self.db.add_all(
                    [
                        AnnotationTask(
                            project_id=project.id,
                            label_studio_task_id=ls_task["id"],
                            data=ls_task["data"],
                            kubeai_object_name=ls_task["data"]["kubeai_object_name"],
                            assigned_to=None,
                            status="unassigned",
                            tenant_id=tenant_id,
                        )
                        for ls_task in ls_tasks
                    ]
                )
                project.total_tasks = len(ls_tasks)
                await self.db.flush()
            except Exception as e:
                logger.warning("导入 LabelStudio tasks 失败, 准备清理项目: %s", e)
                await self.ls_client.delete_project(ls_project_id)
                raise ExternalServiceException(f"导入 LabelStudio tasks 失败: {e}") from e

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

    async def sync_project_tasks(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> int:
        """Sync new files from the dataset version into the annotation project."""
        result = await self.db.execute(
            select(AnnotationProject)
            .options(selectinload(AnnotationProject.dataset), selectinload(AnnotationProject.dataset_version))
            .where(AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundException("标注项目不存在")

        ls_project_id = project.label_studio_project_id
        if ls_project_id is None:
            raise ExternalServiceException("LabelStudio 项目 ID 不存在")

        dataset = project.dataset
        version = project.dataset_version
        tenant_name = await self._get_tenant_name(tenant_id)
        prefix = f"datasets/{dataset.name}/v{version.version_number}/"

        # List current MinIO objects
        objects = await self.minio.list_objects(tenant_name, prefix)
        if not objects:
            return 0

        # Get existing object names for deduplication
        existing_result = await self.db.execute(
            select(AnnotationTask.kubeai_object_name).where(AnnotationTask.project_id == project_id)
        )
        existing_names = set(existing_result.scalars().all())

        # Filter to only new objects
        new_objects = [obj for obj in objects if obj["object_name"] not in existing_names]
        if not new_objects:
            return 0

        # Prepare and import new tasks
        config_info = parse_label_config(project.label_config)
        tasks = await self._prepare_task_data(new_objects, prefix, config_info, tenant_name)
        ls_tasks = await self._import_tasks_batched(ls_project_id, tasks)

        self.db.add_all(
            [
                AnnotationTask(
                    project_id=project.id,
                    label_studio_task_id=ls_task["id"],
                    data=ls_task["data"],
                    kubeai_object_name=ls_task["data"]["kubeai_object_name"],
                    assigned_to=None,
                    status="unassigned",
                    tenant_id=tenant_id,
                )
                for ls_task in ls_tasks
            ]
        )
        project.total_tasks = (project.total_tasks or 0) + len(ls_tasks)
        await self.db.flush()

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(project.id),
                detail={"action": "sync_tasks", "new_task_count": len(ls_tasks)},
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.commit()
        return len(ls_tasks)

    async def _prepare_task_data(
        self,
        objects: list[dict[str, Any]],
        prefix: str,
        config_info: Any,
        tenant_name: str,
    ) -> list[dict[str, Any]]:
        """Build task data dicts with concurrent MinIO operations."""
        data_object = get_primary_data_object(config_info)
        semaphore = asyncio.Semaphore(_MINIO_CONCURRENCY)

        async def _build_one(obj: dict[str, Any]) -> dict[str, Any]:
            object_name = obj["object_name"]
            file_name = object_name.removeprefix(prefix)
            data: dict[str, Any] = {
                "kubeai_object_name": object_name,
                "kubeai_file_name": file_name,
                "kubeai_content_type": obj.get("content_type", "application/octet-stream"),
            }
            async with semaphore:
                if data_object.tag in URL_OBJECT_TAGS:
                    data[data_object.field] = await self.minio.presigned_get_url(tenant_name, object_name)
                elif data_object.tag in TEXT_OBJECT_TAGS:
                    content = await self.minio.get_object_content(tenant_name, object_name)
                    data[data_object.field] = content.decode("utf-8", errors="replace")
            return {"data": data}

        results = await asyncio.gather(*[_build_one(obj) for obj in objects])
        return list(results)

    async def _import_tasks_batched(self, ls_project_id: int, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Import tasks to LabelStudio in batches and return all LS task records."""
        all_ls_tasks: list[dict[str, Any]] = []
        for i in range(0, len(tasks), _LS_BATCH_SIZE):
            batch = tasks[i : i + _LS_BATCH_SIZE]
            ls_tasks = await self.ls_client.import_tasks(ls_project_id, batch)
            all_ls_tasks.extend(ls_tasks)
        return all_ls_tasks

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

        try:
            from app.models.enums import NotificationPriority, NotificationType
            from app.services.notification_service import NotificationService

            notif_service = NotificationService(self.db)
            project = await self.db.get(AnnotationProject, project_id)
            project_name = project.name if project else "未知项目"
            await notif_service.create_notification(
                user_id=request.user_id,
                tenant_id=tenant_id,
                type=NotificationType.ANNOTATION_TASK,
                title="标注任务分配",
                content=f"您在项目「{project_name}」中被分配了 {len(tasks)} 个标注任务.",
                priority=NotificationPriority.MEDIUM,
                resource_type="annotation_project",
                resource_id=str(project_id),
            )
        except Exception as e:
            logger.warning("Failed to send annotation notification: %s", e)

        return len(tasks)

    async def unassign_tasks(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        request: AnnotationTaskUnassignRequest,
        audit_context: dict[str, Any] | None = None,
    ) -> int:
        await self._validate_project_membership(project_id, tenant_id)

        result = await self.db.execute(
            select(AnnotationTask).where(
                AnnotationTask.id.in_(request.task_ids),
                AnnotationTask.project_id == project_id,
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.status == "assigned",
            )
        )
        tasks = list(result.scalars().all())

        if len(tasks) != len(request.task_ids):
            found_ids = {t.id for t in tasks}
            missing = set(request.task_ids) - found_ids
            raise ForbiddenException(f"以下任务不存在或当前状态不可取消分配: {missing}")

        for task in tasks:
            task.assigned_to = None
            task.status = "unassigned"

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(project_id),
                detail={"action": "unassign_tasks", "task_count": len(tasks)},
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

        try:
            from collections import Counter

            from app.models.enums import NotificationPriority, NotificationType
            from app.services.notification_service import NotificationService

            notif_service = NotificationService(self.db)
            project = await self.db.get(AnnotationProject, project_id)
            project_name = project.name if project else "未知项目"
            user_task_counts = Counter(request.user_ids[i % len(request.user_ids)] for i in range(total_to_assign))
            for uid, count in user_task_counts.items():
                await notif_service.create_notification(
                    user_id=uid,
                    tenant_id=tenant_id,
                    type=NotificationType.ANNOTATION_TASK,
                    title="标注任务分配",
                    content=f"您在项目「{project_name}」中被分配了 {count} 个标注任务.",
                    priority=NotificationPriority.MEDIUM,
                    resource_type="annotation_project",
                    resource_id=str(project_id),
                )
        except Exception as e:
            logger.warning("Failed to send batch annotation notifications: %s", e)

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

        # Auto-trigger callback when all tasks completed
        should_callback = (
            project.total_tasks > 0
            and project.completed_tasks >= project.total_tasks
            and project.callback_status == "pending"
        )
        if should_callback:
            try:
                await self._trigger_callback(project, tenant_id)
            except Exception as e:
                logger.error("标注回流自动触发失败 project=%s: %s", project.id, e)

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

    async def retry_callback(
        self, project_id: uuid.UUID, tenant_id: uuid.UUID, user_id: uuid.UUID
    ) -> AnnotationProject:
        result = await self.db.execute(
            select(AnnotationProject)
            .options(selectinload(AnnotationProject.dataset), selectinload(AnnotationProject.dataset_version))
            .where(AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            raise NotFoundException("标注项目不存在")
        if project.callback_status != "failed":
            raise ForbiddenException("只能重试失败的回流任务")

        project.callback_status = "pending"
        project.callback_error = None
        project.callback_progress = 0
        await self.db.flush()

        await self._trigger_callback(project, tenant_id)
        return project

    async def _trigger_callback(self, project: AnnotationProject, tenant_id: uuid.UUID) -> None:
        if project.status != "active":
            raise ForbiddenException("项目状态不是活跃, 无法触发回流")
        if project.total_tasks <= 0 or project.completed_tasks < project.total_tasks:
            raise ForbiddenException("标注任务尚未全部完成")

        project.callback_status = "running"
        project.callback_progress = 0
        await self.db.flush()

        try:
            # 1. Export annotations from LabelStudio
            if project.label_studio_project_id is None:
                raise ExternalServiceException("LabelStudio 项目 ID 不存在")
            annotations = await self.ls_client.export_project_annotations(project.label_studio_project_id)
            project.callback_progress = 10
            await self.db.flush()

            # 2. Get source dataset/version info
            dataset = project.dataset
            source_version = project.dataset_version
            tenant_name = await self._get_tenant_name(tenant_id)

            # 3. Create new dataset version
            from app.services.dataset_service import DatasetService

            ds_service = DatasetService(self.db, self.minio)
            description = f"v{source_version.version_number}-annotated"
            new_version = await ds_service.create_version(
                tenant_id=tenant_id,
                dataset_id=dataset.id,
                user_id=project.created_by,
                description=description,
            )
            project.callback_progress = 20
            await self.db.flush()

            # 4. Copy original files from source version to new version
            src_prefix = f"datasets/{dataset.name}/v{source_version.version_number}/"
            dst_prefix = f"datasets/{dataset.name}/v{new_version.version_number}/"

            objects = await self.minio.list_objects(tenant_name, src_prefix)
            total_objects = len(objects)
            for i, obj in enumerate(objects):
                src_name = obj["object_name"]
                file_name = src_name.removeprefix(src_prefix)
                if not file_name:
                    continue
                await self.minio.copy_object(
                    src_tenant=tenant_name,
                    src_object=src_name,
                    dst_tenant=tenant_name,
                    dst_object=f"{dst_prefix}{file_name}",
                )
                progress = 20 + int((i + 1) / max(total_objects, 1) * 70)
                project.callback_progress = min(progress, 90)
                await self.db.flush()

            # 5. Write annotations.json
            export_data = {
                "project_name": project.name,
                "annotation_type": project.annotation_type,
                "source_dataset_id": str(dataset.id),
                "source_version_id": str(source_version.id),
                "exported_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
                "total_tasks": project.total_tasks,
                "annotations": annotations,
            }
            annotations_bytes = json.dumps(export_data, ensure_ascii=False, indent=2).encode("utf-8")
            await self.minio.upload_stream(
                tenant_name,
                f"{dst_prefix}annotations.json",
                BytesIO(annotations_bytes),
                len(annotations_bytes),
                "application/json",
            )

            # 6. Update new version file count and size
            new_objects = await self.minio.list_objects(tenant_name, dst_prefix)
            new_version.file_count = len(new_objects)
            new_version.total_size_bytes = sum(o.get("size", 0) for o in new_objects)

            # 7. Mark callback succeeded
            project.callback_status = "succeeded"
            project.callback_progress = 100
            project.callback_version_id = new_version.id
            project.callback_at = datetime.now(timezone.utc)  # noqa: UP017
            project.status = "completed"
            await self.db.flush()
            await self.db.commit()

        except Exception as e:
            project.callback_status = "failed"
            project.callback_error = str(e)
            logger.error("标注回流失败 project=%s: %s", project.id, e, exc_info=True)
            await self.db.flush()
            await self.db.commit()
            raise

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
        config_info = parse_label_config(project.label_config)
        data = dict(task.data)
        object_name = data.get("kubeai_object_name")

        if object_name:
            for data_object in config_info.objects:
                if data_object.tag in URL_OBJECT_TAGS:
                    data[data_object.field] = await self.minio.presigned_get_url(tenant_name, object_name)

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
