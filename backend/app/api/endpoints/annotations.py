import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.clients import get_labelstudio_client
from app.integrations.labelstudio.client import LabelStudioClient
from app.schemas.annotation import (
    AnnotationBatchAssignRequest,
    AnnotationProjectCreateRequest,
    AnnotationProjectDetailResponse,
    AnnotationProjectResponse,
    AnnotationSubmitRequest,
    AnnotationTaskAssignRequest,
    AnnotationTaskResponse,
    AnnotationTaskSummaryResponse,
    AnnotationTaskUnassignRequest,
    MyTaskIdsResponse,
    SyncTasksResponse,
)
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.services.annotation_service import AnnotationService
from app.tasks.annotation_tasks import enqueue_annotation_project_create, enqueue_annotation_project_sync

router = APIRouter(prefix="/annotations", tags=["annotations"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
LabelStudioDep = Annotated[LabelStudioClient, Depends(lambda: get_labelstudio_client())]
_keyword_query = Query(None)
_status_query: str | None = Query(None)
_assigned_to_query: uuid.UUID | None = Query(None)


def _audit_ctx(request: Request, user: Any) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


def _require_tenant_id(user: Any) -> uuid.UUID:
    if user.tenant_id is None:
        from app.core.exceptions import ForbiddenException

        raise ForbiddenException("请先加入租户")
    return uuid.UUID(str(user.tenant_id))


def _build_project_response(project: Any) -> AnnotationProjectResponse:
    dataset = project.dataset
    version = project.dataset_version
    template = project.template
    total = project.total_tasks or 0
    completed = project.completed_tasks or 0
    progress = round((completed / total * 100) if total > 0 else 0, 1)

    return AnnotationProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        dataset_id=project.dataset_id,
        dataset_version_id=project.dataset_version_id,
        template_id=project.template_id,
        template_name=template.name if template else None,
        label_studio_project_id=project.label_studio_project_id,
        total_tasks=total,
        completed_tasks=completed,
        status=project.status,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        tenant_id=project.tenant_id,
        dataset_name=dataset.name if dataset else None,
        dataset_version_number=version.version_number if version else None,
        progress_percent=progress,
    )


@router.post("/projects", response_model=BaseResponse[AnnotationProjectDetailResponse])
async def create_project(
    req: AnnotationProjectCreateRequest,
    db: DbDep,
    ls: LabelStudioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[AnnotationProjectDetailResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    project = await service.create_project(
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        description=req.description,
        dataset_id=req.dataset_id,
        dataset_version_id=req.dataset_version_id,
        template_id=req.template_id,
        audit_context=_audit_ctx(request, user),
    )
    await enqueue_annotation_project_create(project.id, tenant_id)
    base = _build_project_response(project)
    detail = AnnotationProjectDetailResponse(
        **base.model_dump(),
        label_config=project.label_config,
        labeling_template_description=None,
    )
    return BaseResponse(data=detail, message="标注项目创建成功")


@router.get("/projects", response_model=PageResponse[AnnotationProjectResponse])
async def list_projects(
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    keyword: str | None = _keyword_query,
    status: str | None = _status_query,
) -> PageResponse[AnnotationProjectResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    items, total = await service.list_projects(
        tenant_id=tenant_id, page=page, page_size=page_size, keyword=keyword, status=status
    )
    project_list = [_build_project_response(p) for p in items]
    page_data = PageData(items=project_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/projects/{project_id}", response_model=BaseResponse[AnnotationProjectDetailResponse])
async def get_project(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
) -> BaseResponse[AnnotationProjectDetailResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    project = await service.get_project(project_id=project_id, tenant_id=tenant_id)
    base = _build_project_response(project)
    detail = AnnotationProjectDetailResponse(
        **base.model_dump(),
        label_config=project.label_config,
        labeling_template_description=None,
    )
    return BaseResponse(data=detail, message="获取成功")


@router.delete("/projects/{project_id}", response_model=BaseResponse[None])
async def delete_project(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    await service.delete_project(
        project_id=project_id,
        tenant_id=tenant_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message="标注项目删除成功")


def _build_task_response(
    task: Any,
    project: Any | None = None,
    assignee: Any | None = None,
    result: list[dict[str, Any]] | None = None,
    submitted_at: datetime | None = None,
    submitted_by: str | None = None,
    annotation_payload: dict[str, Any] | None = None,
) -> AnnotationTaskResponse:
    template = project.template if project else None
    return AnnotationTaskResponse(
        id=task.id,
        project_id=task.project_id,
        label_studio_task_id=task.label_studio_task_id,
        data=task.data,
        assigned_to=task.assigned_to,
        assigned_to_name=assignee.username if assignee else None,
        status=task.status,
        project_name=project.name if project else None,
        template_name=template.name if template else None,
        result=result,
        submitted_at=submitted_at,
        submitted_by=uuid.UUID(submitted_by) if submitted_by else None,
        annotation_payload=annotation_payload,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


async def _build_task_response_with_payload(service: AnnotationService, task: Any) -> AnnotationTaskResponse:
    """Build the response using the verbatim annotation file payload.

    The payload is passed through as ``annotation_payload`` so the client can
    display the on-disk JSON 1:1; ``result``/``submitted_at``/``submitted_by``
    are echoed back as first-class fields for convenience but no extra
    derivation is performed.
    """
    payload = await service.load_persisted_annotation(task)
    if payload is None:
        return _build_task_response(task, task.project, task.assignee)
    submitted_by_raw = payload.get("submitted_by")
    submitted_by = str(submitted_by_raw) if submitted_by_raw is not None else None
    raw_result = payload.get("result")
    result_list = raw_result if isinstance(raw_result, list) else None

    submitted_at: datetime | None = None
    raw_submitted_at = payload.get("submitted_at")
    if isinstance(raw_submitted_at, str):
        try:
            submitted_at = datetime.fromisoformat(raw_submitted_at)
        except ValueError:
            submitted_at = None

    return _build_task_response(
        task,
        task.project,
        task.assignee,
        result=result_list,
        submitted_at=submitted_at,
        submitted_by=submitted_by,
        annotation_payload=payload,
    )


@router.get("/projects/{project_id}/tasks", response_model=PageResponse[AnnotationTaskResponse])
async def list_project_tasks(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = _status_query,
    assigned_to: uuid.UUID | None = _assigned_to_query,
) -> PageResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    tasks, total = await service.list_project_tasks(
        project_id=project_id,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        assigned_to=assigned_to,
    )
    task_list = [await _build_task_response_with_payload(service, t) for t in tasks]
    page_data = PageData(items=task_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.post("/projects/{project_id}/assign", response_model=BaseResponse[None])
async def assign_tasks(
    project_id: uuid.UUID,
    req: AnnotationTaskAssignRequest,
    db: DbDep,
    ls: LabelStudioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    count = await service.assign_tasks(
        project_id=project_id,
        tenant_id=tenant_id,
        request=req,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message=f"成功分配 {count} 个任务")


@router.post("/projects/{project_id}/unassign", response_model=BaseResponse[None])
async def unassign_tasks(
    project_id: uuid.UUID,
    req: AnnotationTaskUnassignRequest,
    db: DbDep,
    ls: LabelStudioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    count = await service.unassign_tasks(
        project_id=project_id,
        tenant_id=tenant_id,
        request=req,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message=f"成功取消分配 {count} 个任务")


@router.post("/projects/{project_id}/batch-assign", response_model=BaseResponse[None])
async def batch_assign_tasks(
    project_id: uuid.UUID,
    req: AnnotationBatchAssignRequest,
    db: DbDep,
    ls: LabelStudioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    count = await service.batch_assign(
        project_id=project_id,
        tenant_id=tenant_id,
        request=req,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message=f"成功均匀分配 {count} 个任务")


@router.get("/my-tasks", response_model=PageResponse[AnnotationTaskResponse])
async def list_my_tasks(
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    status: str | None = Query(None),
    keyword: str | None = Query(None),
) -> PageResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    tasks, total = await service.list_my_tasks(
        tenant_id=tenant_id,
        user_id=user.id,
        page=page,
        page_size=page_size,
        status=status,
        keyword=keyword,
    )
    task_list = [await _build_task_response_with_payload(service, t) for t in tasks]
    page_data = PageData(items=task_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/my-tasks/summary", response_model=BaseResponse[list[AnnotationTaskSummaryResponse]])
async def get_my_task_summary(
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
) -> BaseResponse[list[AnnotationTaskSummaryResponse]]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    rows = await service.get_my_task_summary(tenant_id=tenant_id, user_id=user.id)
    summary_list = [AnnotationTaskSummaryResponse(**row) for row in rows]
    return BaseResponse(data=summary_list, message="获取成功")


@router.post("/tasks/{task_id}/start", response_model=BaseResponse[AnnotationTaskResponse])
async def start_annotation(
    task_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "write"))],
) -> BaseResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    task = await service.start_annotation(
        task_id=task_id,
        tenant_id=tenant_id,
        user_id=user.id,
    )
    return BaseResponse(
        data=await _build_task_response_with_payload(service, task),
        message="开始标注",
    )


@router.post("/tasks/{task_id}/submit", response_model=BaseResponse[AnnotationTaskResponse])
async def submit_annotation(
    task_id: uuid.UUID,
    req: AnnotationSubmitRequest,
    db: DbDep,
    ls: LabelStudioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "write"))],
) -> BaseResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    task = await service.submit_annotation(
        task_id=task_id,
        tenant_id=tenant_id,
        user_id=user.id,
        result=req.result,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(
        data=await _build_task_response_with_payload(service, task),
        message="标注提交成功",
    )


@router.get("/projects/{project_id}/my-task-ids", response_model=BaseResponse[MyTaskIdsResponse])
async def list_my_project_task_ids(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
) -> BaseResponse[MyTaskIdsResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    task_ids, completed_count = await service.list_my_task_ids(
        project_id=project_id,
        tenant_id=tenant_id,
        user_id=user.id,
    )
    return BaseResponse(
        data=MyTaskIdsResponse(task_ids=task_ids, completed_count=completed_count),
        message="获取成功",
    )


@router.get("/projects/{project_id}/next-task", response_model=BaseResponse[AnnotationTaskResponse | None])
async def get_next_annotation_task(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "write"))],
) -> BaseResponse[AnnotationTaskResponse | None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    task = await service.get_next_task(
        project_id=project_id,
        tenant_id=tenant_id,
        user_id=user.id,
    )
    if task is None:
        return BaseResponse(data=None, message="没有更多待标注任务")
    return BaseResponse(
        data=await _build_task_response_with_payload(service, task),
        message="获取成功",
    )


@router.get("/tasks/{task_id}", response_model=BaseResponse[AnnotationTaskResponse])
async def get_annotation_task_detail(
    task_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
) -> BaseResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    task = await service.get_task_detail(
        task_id=task_id,
        tenant_id=tenant_id,
    )
    return BaseResponse(
        data=await _build_task_response_with_payload(service, task),
        message="获取成功",
    )


@router.post("/tasks/{task_id}/cancel", response_model=BaseResponse[AnnotationTaskResponse])
async def cancel_annotation(
    task_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "write"))],
) -> BaseResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    task = await service.cancel_annotation(
        task_id=task_id,
        tenant_id=tenant_id,
        user_id=user.id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(
        data=await _build_task_response_with_payload(service, task),
        message="标注已取消",
    )


@router.post("/projects/{project_id}/sync-tasks", response_model=BaseResponse[SyncTasksResponse])
async def sync_project_tasks(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[SyncTasksResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    # Validate project exists
    await service.get_project(project_id=project_id, tenant_id=tenant_id)
    await enqueue_annotation_project_sync(project_id, tenant_id)
    return BaseResponse(
        data=SyncTasksResponse(synced_count=0),
        message="任务同步已提交",
    )


@router.post("/projects/{project_id}/retry", response_model=BaseResponse[AnnotationProjectDetailResponse])
async def retry_project(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[AnnotationProjectDetailResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls)
    project = await service.retry_project(project_id=project_id, tenant_id=tenant_id)
    await enqueue_annotation_project_create(project.id, tenant_id)
    base = _build_project_response(project)
    detail = AnnotationProjectDetailResponse(
        **base.model_dump(),
        label_config=project.label_config,
        labeling_template_description=None,
    )
    return BaseResponse(data=detail, message="项目重试已启动")
