from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictException, ExternalServiceException, ForbiddenException, NotFoundException
from app.integrations.base import sanitize_k8s_name
from app.integrations.labelstudio.templates import (
    TEXT_OBJECT_TAGS,
    URL_OBJECT_TAGS,
    get_primary_data_object,
    parse_label_config,
)
from app.integrations.storage.filesystem import FileSystemStorage
from app.models.annotation import AnnotationProject
from app.models.annotation_task import AnnotationTask
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import AnnotationProjectStatus, AuditAction, ResourceType
from app.models.tenant import Tenant
from app.models.user import User
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.integrations.labelstudio.client import LabelStudioClient
    from app.schemas.annotation import (
        AnnotationBatchAssignRequest,
        AnnotationTaskAssignRequest,
        AnnotationTaskUnassignRequest,
    )

logger = logging.getLogger(__name__)

_LS_BATCH_SIZE = 250


def _annotation_filename(kubeai_object_name: str) -> str:
    """kubeai_object_name 形如 'datasets/<tenant>/<dataset>/v<n>/a.jpg' -> 'a.jpg.json'."""
    return Path(kubeai_object_name).name + ".json"


async def _load_annotation_result(
    storage: FileSystemStorage, tenant_name: str, dataset_name: str, version_number: int, kubeai_object_name: str
) -> dict[str, Any] | None:
    """Load the full annotation payload written to annotations/<file>.json verbatim.

    Returns None when the task has not yet been submitted or the file is missing/unreadable.
    The returned dict matches the on-disk JSON exactly — no field is rewritten.
    """
    annotation_filename = _annotation_filename(kubeai_object_name)
    annotation_path = storage.get_file_path(
        tenant_name, dataset_name, version_number, f"annotations/{annotation_filename}"
    )
    if not annotation_path.exists():
        return None
    try:
        raw = await storage.get_file_content(annotation_path)
        payload = json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("annotation_result_load_failed path=%s: %s", annotation_path, e)
        return None
    if not isinstance(payload, dict):
        return None
    return payload


class AnnotationService:
    def __init__(self, db: AsyncSession, labelstudio_client: LabelStudioClient) -> None:
        self.db = db
        self.ls_client = labelstudio_client
        self.storage = FileSystemStorage()

    async def _get_tenant_name(self, tenant_id: uuid.UUID) -> str:
        result = await self.db.execute(select(Tenant.name).where(Tenant.id == tenant_id))
        name = result.scalar_one_or_none()
        if not name:
            raise NotFoundException("租户不存在")
        return name

    def _build_download_url(self, dataset_id: uuid.UUID, version_id: uuid.UUID, file_name: str) -> str:
        return f"/api/datasets/{dataset_id}/versions/{version_id}/files/{file_name}/download"

    async def create_project(
        self,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        name: str,
        description: str | None,
        dataset_id: uuid.UUID,
        dataset_version_id: uuid.UUID,
        template_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> AnnotationProject:
        """创建标注项目 DB 记录 (仅验证 + 记录, LabelStudio 交互由 Taskiq worker 异步执行)."""
        await self._get_dataset_or_fail(dataset_id, tenant_id)
        await self._get_version_or_fail(dataset_version_id, dataset_id)

        from app.models.annotation_template import AnnotationTemplate

        result = await self.db.execute(
            select(AnnotationTemplate).where(
                AnnotationTemplate.id == template_id,
                AnnotationTemplate.tenant_id == tenant_id,
            )
        )
        tpl = result.scalar_one_or_none()
        if tpl is None:
            raise NotFoundException("标注模板不存在")

        # 双保险: 即使模板创建时已校验过, 项目创建时再解析一次防止 XML 被中途篡改
        parse_label_config(tpl.label_config)

        project = AnnotationProject(
            name=name,
            description=description,
            dataset_id=dataset_id,
            dataset_version_id=dataset_version_id,
            template_id=tpl.id,
            label_studio_project_id=None,
            label_config=tpl.label_config,  # 拍快照, 模板后续编辑不影响该项目
            total_tasks=0,
            completed_tasks=0,
            status=AnnotationProjectStatus.PENDING,
            tenant_id=tenant_id,
            created_by=user_id,
        )
        project.template = tpl  # template 关系是 lazy="noload", 主动装上供响应构建读取
        self.db.add(project)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise ConflictException(f"标注项目名称 '{name}' 已存在, 请更换名称") from exc

        await self.db.refresh(project)

        if audit_context:
            await self._log_audit(
                action=AuditAction.CREATE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(project.id),
                detail={"name": name, "template_name": tpl.name},
                tenant_id=tenant_id,
                **audit_context,
            )

        await self.db.commit()
        return project

    async def execute_project_setup(self, project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """由 Taskiq worker 调用: 枚举文件 + 创建 LabelStudio 项目 + 导入任务."""
        from app.models.annotation_task import AnnotationTask

        result = await self.db.execute(
            select(AnnotationProject)
            .options(selectinload(AnnotationProject.dataset), selectinload(AnnotationProject.dataset_version))
            .where(AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return
        # 幂等守卫: stream 未确认消息会被重投, 重复投递时已成功/已失败的项目直接跳过
        if project.status != AnnotationProjectStatus.PENDING:
            return
        assert project.label_config is not None, "execute_project_setup requires label_config snapshot"

        dataset = project.dataset
        version = project.dataset_version
        tenant_name = await self._get_tenant_name(tenant_id)

        # Enumerate files from filesystem
        files = await self.storage.list_files(tenant_name, dataset.name, version.version_number)
        if not files:
            project.status = AnnotationProjectStatus.ACTIVE
            await self.db.commit()
            return

        # Prepare task data
        config_info = parse_label_config(project.label_config)
        tasks = await self._prepare_task_data(
            files,
            dataset.id,
            version.id,
            config_info,
            tenant_name,
            dataset.name,
            version.version_number,
        )

        # Create project in LabelStudio
        try:
            ls_project_id = await self.ls_client.create_project(
                project.name,
                project.description or "",
                project.label_config or "",
            )
        except ExternalServiceException:
            await self._mark_project_failed(project_id, tenant_id)
            raise
        except Exception as e:
            await self._mark_project_failed(project_id, tenant_id)
            raise ExternalServiceException(f"创建 LabelStudio 项目失败: {e}") from e

        project.label_studio_project_id = ls_project_id

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
            except Exception as e:
                logger.warning("导入 LabelStudio tasks 失败, 准备清理项目: %s", e)
                await self.ls_client.delete_project(ls_project_id)
                await self._mark_project_failed(project_id, tenant_id)
                raise ExternalServiceException(f"导入 LabelStudio tasks 失败: {e}") from e

        project.status = AnnotationProjectStatus.ACTIVE
        await self.db.commit()

    async def _mark_project_failed(self, project_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """失败状态独立事务落库: 先 rollback 丢弃半途状态(含未提交的 LS 项目 id), 再置 failed.

        不复用 session 内的 ORM 对象: rollback 会过期属性, 异步上下文访问触发懒加载会抛
        MissingGreenlet, 因此用 UPDATE 语句直接写.
        """
        await self.db.rollback()
        await self.db.execute(
            update(AnnotationProject)
            .where(AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id)
            .values(status=AnnotationProjectStatus.FAILED)
        )
        await self.db.commit()

    async def execute_sync_tasks(self, project_id: uuid.UUID, tenant_id: uuid.UUID) -> int:
        """由 Taskiq worker 调用: 同步新文件到标注项目."""
        from app.models.annotation_task import AnnotationTask

        result = await self.db.execute(
            select(AnnotationProject)
            .options(selectinload(AnnotationProject.dataset), selectinload(AnnotationProject.dataset_version))
            .where(AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id)
        )
        project = result.scalar_one_or_none()
        if not project:
            return 0

        ls_project_id = project.label_studio_project_id
        if ls_project_id is None:
            return 0
        assert project.label_config is not None, "execute_sync_tasks requires label_config snapshot"

        dataset = project.dataset
        version = project.dataset_version
        tenant_name = await self._get_tenant_name(tenant_id)

        files = await self.storage.list_files(tenant_name, dataset.name, version.version_number)
        if not files:
            return 0

        existing_result = await self.db.execute(
            select(AnnotationTask.kubeai_object_name).where(AnnotationTask.project_id == project_id)
        )
        # kubeai_object_name is e.g. "datasets/tenant_name/dataset_name/v1/file.jpg"
        # extract the base file name for deduplication against storage file names
        existing_names = {name.rsplit("/", 1)[-1] if "/" in name else name for name in existing_result.scalars().all()}

        new_files = [f for f in files if f["file_name"] not in existing_names]
        if not new_files:
            return 0

        config_info = parse_label_config(project.label_config)
        tasks = await self._prepare_task_data(
            new_files,
            dataset.id,
            version.id,
            config_info,
            tenant_name,
            dataset.name,
            version.version_number,
        )
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
        await self.db.commit()
        return len(ls_tasks)

    _STRUCTURED_EXTENSIONS = frozenset({".json", ".jsonl", ".csv"})

    async def _prepare_task_data(
        self,
        files: list[dict[str, Any]],
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        config_info: Any,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
    ) -> list[dict[str, Any]]:
        """Build task data dicts from filesystem files.

        Single-object config (1 $field): one task per file, file content → the field.
        Multi-object config (>1 $field): only structured files (JSON/JSONL/CSV),
        each record → one task with all fields populated from the record.
        """
        if len(config_info.objects) > 1:
            return await self._prepare_multi_object_tasks(
                files,
                dataset_id,
                version_id,
                config_info,
                tenant_name,
                dataset_name,
                version_number,
            )
        return await self._prepare_single_object_tasks(
            files,
            dataset_id,
            version_id,
            config_info,
            tenant_name,
            dataset_name,
            version_number,
        )

    async def _prepare_single_object_tasks(
        self,
        files: list[dict[str, Any]],
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        config_info: Any,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
    ) -> list[dict[str, Any]]:
        data_object = get_primary_data_object(config_info)

        results: list[dict[str, Any]] = []
        for f in files:
            file_name = f["file_name"]
            object_name = f"datasets/{sanitize_k8s_name(tenant_name)}/{sanitize_k8s_name(dataset_name)}/v{version_number}/{file_name}"
            data: dict[str, Any] = {
                "kubeai_object_name": object_name,
                "kubeai_file_name": file_name,
                "kubeai_content_type": f.get("content_type", "application/octet-stream"),
            }

            if data_object.tag in URL_OBJECT_TAGS:
                data[data_object.field] = self._build_download_url(dataset_id, version_id, file_name)
            elif data_object.tag in TEXT_OBJECT_TAGS:
                file_path = self.storage.get_file_path(tenant_name, dataset_name, version_number, file_name)
                content = await self.storage.get_file_content(file_path)
                data[data_object.field] = content.decode("utf-8", errors="replace")

            results.append({"data": data})

        return results

    async def _prepare_multi_object_tasks(
        self,
        files: list[dict[str, Any]],
        dataset_id: uuid.UUID,
        version_id: uuid.UUID,
        config_info: Any,
        tenant_name: str,
        dataset_name: str,
        version_number: int,
    ) -> list[dict[str, Any]]:
        """Multi-object: parse structured files, each record = one task with all fields."""
        field_map: dict[str, str] = {obj.field: obj.tag for obj in config_info.objects}
        required_fields: list[str] = list(field_map)

        results: list[dict[str, Any]] = []
        for f in files:
            file_name: str = f["file_name"]
            ext = Path(file_name).suffix.lower()
            if ext not in self._STRUCTURED_EXTENSIONS:
                logger.warning("multi_object_skip_non_structured file=%s", file_name)
                continue

            file_path = self.storage.get_file_path(tenant_name, dataset_name, version_number, file_name)
            raw = await self.storage.get_file_content(file_path)
            records = self._parse_structured_content(raw, file_name, ext)

            for idx, record in enumerate(records):
                missing = [k for k in required_fields if k not in record]
                if missing:
                    raise ExternalServiceException(
                        f"文件 '{file_name}' 第 {idx + 1} 条记录缺少必填字段: {', '.join(missing)}"
                    )

                object_name = (
                    f"datasets/{sanitize_k8s_name(tenant_name)}/{sanitize_k8s_name(dataset_name)}"
                    f"/v{version_number}/{file_name}#row{idx}"
                )
                data: dict[str, Any] = {
                    "kubeai_object_name": object_name,
                    "kubeai_file_name": file_name,
                    "kubeai_content_type": "application/json",
                }

                for field_name, tag in field_map.items():
                    value = record[field_name]
                    if tag in URL_OBJECT_TAGS:
                        # Resolve relative paths to download URLs, pass absolute URLs through
                        value_str = str(value)
                        if not (
                            value_str.startswith("http://")
                            or value_str.startswith("https://")
                            or value_str.startswith("/")
                        ):
                            value = self._build_download_url(dataset_id, version_id, value_str)
                    data[field_name] = value

                results.append({"data": data})

        if not results:
            logger.warning(
                "multi_object_no_structured_files files=%d objects=%s",
                len(files),
                [obj.field for obj in config_info.objects],
            )

        return results

    @staticmethod
    def _parse_structured_content(raw: bytes, file_name: str, ext: str) -> list[dict[str, Any]]:
        """Parse structured file content into list of record dicts."""
        text = raw.decode("utf-8", errors="replace")
        try:
            if ext == ".json":
                records: Any = json.loads(text)
                if isinstance(records, dict):
                    records = [records]
                if not isinstance(records, list):
                    raise ValueError("JSON 文件顶层必须是对象或数组")
                return records
            elif ext == ".jsonl":
                return [json.loads(line) for line in text.splitlines() if line.strip()]
            elif ext == ".csv":
                reader = csv.DictReader(io.StringIO(text))
                return list(reader)
        except (json.JSONDecodeError, ValueError) as e:
            raise ExternalServiceException(f"解析文件 '{file_name}' 失败: {e}") from e

        raise ValueError(f"不支持的文件类型: {ext}")

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
            .options(
                selectinload(AnnotationProject.dataset),
                selectinload(AnnotationProject.dataset_version),
                selectinload(AnnotationProject.template),
            )
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
            .options(
                selectinload(AnnotationProject.dataset),
                selectinload(AnnotationProject.dataset_version),
                selectinload(AnnotationProject.template),
            )
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

    async def retry_project(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> AnnotationProject:
        """Reset a failed annotation project to pending and prepare for retry.

        Only projects in 'failed' status can be retried. Stale LabelStudio
        resources from the prior attempt are cleaned up on a best-effort basis.
        """
        project = await self._validate_project_membership(project_id, tenant_id)

        if project.status != AnnotationProjectStatus.FAILED:
            raise ConflictException(f"当前状态为 {project.status}，仅失败的项目可以重试")

        # 残留 LabelStudio 项目尽力清理; delete_project 内部吞掉所有异常只记日志, 这里不会再抛
        if project.label_studio_project_id is not None:
            await self.ls_client.delete_project(project.label_studio_project_id)

        # Reset project state for a fresh setup attempt.
        project.status = AnnotationProjectStatus.PENDING
        project.label_studio_project_id = None
        project.total_tasks = 0
        project.completed_tasks = 0
        await self.db.commit()

        return project

    async def _sync_project_stats(self, project: AnnotationProject) -> None:
        if project.label_studio_project_id is None:
            return
        try:
            stats = await self.ls_client.get_project_stats(project.label_studio_project_id)
            project.total_tasks = stats.get("total", project.total_tasks)
            project.completed_tasks = stats.get("completed", project.completed_tasks)
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
            .options(
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.template),
                selectinload(AnnotationTask.assignee),
            )
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
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[AnnotationTask], int]:
        conditions: list[Any] = [
            AnnotationTask.tenant_id == tenant_id,
            AnnotationTask.assigned_to == user_id,
        ]
        if status:
            conditions.append(AnnotationTask.status == status)
        if keyword:
            conditions.append(AnnotationProject.name.ilike(f"%{keyword}%"))

        query = (
            select(AnnotationTask)
            .join(AnnotationProject, AnnotationTask.project_id == AnnotationProject.id)
            .options(
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.template),
                selectinload(AnnotationTask.assignee),
            )
            .where(*conditions)
            .order_by(AnnotationTask.created_at.desc(), AnnotationTask.label_studio_task_id.desc())
        )

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(query.offset((page - 1) * page_size).limit(page_size))
        return list(result.scalars().all()), total

    async def list_my_task_ids(
        self,
        project_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> tuple[list[uuid.UUID], int]:
        """返回当前用户在项目内的任务 ID 列表(稳定升序)与已完成数,用于工作台线性导航与进度。

        排序以 (created_at, label_studio_task_id) 保证批量导入(同一时间戳)时顺序确定,
        否则任务序号会在多次查询间漂移。
        """
        await self._validate_project_membership(project_id, tenant_id)
        result = await self.db.execute(
            select(AnnotationTask.id, AnnotationTask.status)
            .where(
                AnnotationTask.project_id == project_id,
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
            )
            .order_by(AnnotationTask.created_at, AnnotationTask.label_studio_task_id)
        )
        rows = result.all()
        ids = [row.id for row in rows]
        completed = sum(1 for row in rows if row.status == "completed")
        return ids, completed

    async def get_my_task_summary(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> list[dict[str, Any]]:
        from app.models.annotation_template import AnnotationTemplate

        result = await self.db.execute(
            select(
                AnnotationTask.project_id,
                AnnotationProject.name.label("project_name"),
                AnnotationTemplate.name.label("template_name"),
                func.count().label("total_tasks"),
                func.count().filter(AnnotationTask.status == "assigned").label("assigned_tasks"),
                func.count().filter(AnnotationTask.status == "completed").label("completed_tasks"),
            )
            .join(AnnotationProject, AnnotationTask.project_id == AnnotationProject.id)
            .outerjoin(AnnotationTemplate, AnnotationProject.template_id == AnnotationTemplate.id)
            .where(
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
            )
            .group_by(AnnotationTask.project_id, AnnotationProject.name, AnnotationTemplate.name)
        )
        rows = result.all()
        return [
            {
                "project_id": row.project_id,
                "project_name": row.project_name,
                "template_name": row.template_name or "—",
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
            return await self._refresh_download_url(task)
        if task.status != "assigned":
            raise ForbiddenException("任务状态不是「已分配」，无法开始标注")
        task.status = "in_progress"
        task = await self._refresh_download_url(task)
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
        if task.status not in ("assigned", "in_progress"):
            raise ForbiddenException("任务状态不是「已分配」或「进行中」，无法提交")

        # 1. Mirror to Label Studio.
        if task.label_studio_task_id:
            await self.ls_client.create_annotation(task.label_studio_task_id, result)

        # 2. Write per-file JSON into the source dataset version's annotations/ dir.
        project = task.project
        dataset = project.dataset
        version = project.dataset_version
        if not (dataset and version and task.kubeai_object_name):
            raise NotFoundException("标注任务缺少关联数据集版本")
        tenant_name = await self._get_tenant_name(tenant_id)

        annotation_filename = _annotation_filename(task.kubeai_object_name)
        annotation_path = self.storage.get_file_path(
            tenant_name,
            dataset.name,
            version.version_number,
            f"annotations/{annotation_filename}",
        )
        payload = {
            "task_id": str(task_id),
            "annotation_project_id": str(project.id),
            "result": result,
            "submitted_at": datetime.now(timezone.utc).isoformat(),  # noqa: UP017
            "submitted_by": str(user_id),
        }
        await self.storage.write_file(
            annotation_path,
            json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
        )

        # 4. Update task + project counters.
        task.status = "completed"
        project.completed_tasks = (project.completed_tasks or 0) + 1
        if (
            project.total_tasks > 0
            and project.completed_tasks >= project.total_tasks
            and project.status == AnnotationProjectStatus.ACTIVE
        ):
            project.status = AnnotationProjectStatus.COMPLETED

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

    async def cancel_annotation(
        self,
        task_id: uuid.UUID,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        audit_context: dict[str, Any] | None = None,
    ) -> AnnotationTask:
        task = await self._get_task_with_project(task_id, tenant_id)
        if task.assigned_to != user_id:
            raise ForbiddenException("只能取消分配给自己的任务")
        if task.status != "completed":
            raise ForbiddenException("只能取消已完成的标注")

        project = task.project
        dataset = project.dataset
        version = project.dataset_version
        tenant_name = await self._get_tenant_name(tenant_id)
        annotation_filename = _annotation_filename(task.kubeai_object_name)
        deleted = await self.storage.delete_file(
            tenant_name,
            dataset.name,
            version.version_number,
            f"annotations/{annotation_filename}",
        )
        if not deleted:
            logger.warning("annotation_file_missing_on_cancel task=%s", task.id)

        task.status = "in_progress"
        project.completed_tasks = max(0, (project.completed_tasks or 0) - 1)
        if project.completed_tasks < project.total_tasks and project.status == AnnotationProjectStatus.COMPLETED:
            project.status = AnnotationProjectStatus.ACTIVE

        if audit_context:
            await self._log_audit(
                action=AuditAction.UPDATE,
                resource_type=ResourceType.ANNOTATION_PROJECT,
                resource_id=str(task.project_id),
                detail={"action": "cancel_annotation", "task_id": str(task_id)},
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
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.template),
                selectinload(AnnotationTask.assignee),
            )
            .where(
                AnnotationTask.project_id == project_id,
                AnnotationTask.tenant_id == tenant_id,
                AnnotationTask.assigned_to == user_id,
                AnnotationTask.status.in_(["in_progress", "assigned"]),
            )
            .order_by(
                case((AnnotationTask.status == "in_progress", 0), else_=1),
                AnnotationTask.created_at,
                AnnotationTask.label_studio_task_id,
            )
            .limit(1)
        )
        task = result.scalar_one_or_none()
        if task is None:
            return None
        return await self._refresh_download_url(task)

    async def get_task_detail(
        self,
        task_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> AnnotationTask:
        task = await self._get_task_with_project(task_id, tenant_id)
        return await self._refresh_download_url(task)

    async def load_persisted_annotation(self, task: AnnotationTask) -> dict[str, Any] | None:
        """Return the verbatim annotation payload for a completed task, None otherwise.

        The returned dict is exactly the JSON written to
        ``annotations/<file>.json`` — no field is rewritten or dropped.
        """
        if task.status != "completed":
            return None
        project = task.project
        dataset = project.dataset if project else None
        version = project.dataset_version if project else None
        if not (dataset and version and task.tenant_id and task.kubeai_object_name):
            return None
        try:
            tenant_name = await self._get_tenant_name(task.tenant_id)
        except NotFoundException:
            return None
        return await _load_annotation_result(
            self.storage,
            tenant_name,
            dataset.name,
            version.version_number,
            task.kubeai_object_name,
        )

    async def _refresh_download_url(self, task: AnnotationTask) -> AnnotationTask:
        """Refresh download URLs in task data for URL-based annotation types."""
        project = task.project
        if not project or not project.dataset or not project.dataset_version or not project.label_config:
            return task

        config_info = parse_label_config(project.label_config)
        data = dict(task.data)
        object_name = data.get("kubeai_object_name")

        if object_name:
            # Strip "#rowN" suffix for multi-object tasks to get the source file name
            file_name = object_name.rsplit("/", 1)[-1] if "/" in object_name else object_name
            if "#" in file_name:
                file_name = file_name.rsplit("#", 1)[0]

            for data_object in config_info.objects:
                if data_object.tag in URL_OBJECT_TAGS:
                    # For multi-object tasks, the field value may already reference a specific file
                    current = data.get(data_object.field)
                    if isinstance(current, str) and not (
                        current.startswith("http://") or current.startswith("https://") or current.startswith("/")
                    ):
                        data[data_object.field] = self._build_download_url(
                            project.dataset.id, project.dataset_version.id, current
                        )
                    elif current is None:
                        # Single-object fallback: rebuild from the source file
                        data[data_object.field] = self._build_download_url(
                            project.dataset.id, project.dataset_version.id, file_name
                        )

        task.data = data
        return task

    async def _get_task_with_project(self, task_id: uuid.UUID, tenant_id: uuid.UUID) -> AnnotationTask:
        result = await self.db.execute(
            select(AnnotationTask)
            .options(
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.dataset),
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.dataset_version),
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.template),
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
                selectinload(AnnotationTask.project).selectinload(AnnotationProject.template),
                selectinload(AnnotationTask.assignee),
            )
            .where(AnnotationTask.id == task_id, AnnotationTask.tenant_id == tenant_id)
            .execution_options(populate_existing=True)
        )
        task = result.scalar_one_or_none()
        if not task:
            raise NotFoundException("标注任务不存在")
        return task

    async def _validate_project_membership(self, project_id: uuid.UUID, tenant_id: uuid.UUID) -> AnnotationProject:
        result = await self.db.execute(
            select(AnnotationProject)
            .options(
                selectinload(AnnotationProject.dataset),
                selectinload(AnnotationProject.dataset_version),
                selectinload(AnnotationProject.template),
            )
            .where(AnnotationProject.id == project_id, AnnotationProject.tenant_id == tenant_id)
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
