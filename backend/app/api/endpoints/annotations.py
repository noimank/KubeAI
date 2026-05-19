import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.events import get_labelstudio_client, get_minio_client
from app.integrations.labelstudio.client import LabelStudioClient
from app.integrations.labelstudio.templates import LABELING_TEMPLATES
from app.integrations.minio import MinIOClient
from app.schemas.annotation import (
    AnnotationBatchAssignRequest,
    AnnotationProjectCreateRequest,
    AnnotationProjectDetailResponse,
    AnnotationProjectResponse,
    AnnotationSubmitRequest,
    AnnotationTaskAssignRequest,
    AnnotationTaskResponse,
    AnnotationTaskSummaryResponse,
    AnnotationTemplateResponse,
)
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.services.annotation_service import AnnotationService

router = APIRouter(prefix="/annotations", tags=["annotations"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
MinioDep = Annotated[MinIOClient, Depends(lambda: get_minio_client())]
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
    total = project.total_tasks or 0
    completed = project.completed_tasks or 0
    progress = round((completed / total * 100) if total > 0 else 0, 1)

    return AnnotationProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        dataset_id=project.dataset_id,
        dataset_version_id=project.dataset_version_id,
        annotation_type=project.annotation_type,
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


@router.get("/templates", response_model=BaseResponse[list[AnnotationTemplateResponse]])
async def get_templates(
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
) -> BaseResponse[list[AnnotationTemplateResponse]]:
    templates = [
        AnnotationTemplateResponse(key=t["key"], label=t["label"], description=t["description"])
        for t in LABELING_TEMPLATES.values()
    ]
    return BaseResponse(data=templates, message="获取成功")


@router.post("/projects", response_model=BaseResponse[AnnotationProjectDetailResponse])
async def create_project(
    req: AnnotationProjectCreateRequest,
    db: DbDep,
    minio: MinioDep,
    ls: LabelStudioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[AnnotationProjectDetailResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    project = await service.create_project(
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        description=req.description,
        dataset_id=req.dataset_id,
        dataset_version_id=req.dataset_version_id,
        annotation_type=req.annotation_type.value,
        audit_context=_audit_ctx(request, user),
    )
    base = _build_project_response(project)
    template = LABELING_TEMPLATES.get(project.annotation_type)
    detail = AnnotationProjectDetailResponse(
        **base.model_dump(),
        label_config=project.label_config,
        labeling_template_description=template["description"] if template else None,
    )
    return BaseResponse(data=detail, message="标注项目创建成功")


@router.get("/projects", response_model=PageResponse[AnnotationProjectResponse])
async def list_projects(
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = _keyword_query,
) -> PageResponse[AnnotationProjectResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    items, total = await service.list_projects(tenant_id=tenant_id, page=page, page_size=page_size, keyword=keyword)
    project_list = [_build_project_response(p) for p in items]
    page_data = PageData(items=project_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/projects/{project_id}", response_model=BaseResponse[AnnotationProjectDetailResponse])
async def get_project(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
) -> BaseResponse[AnnotationProjectDetailResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    project = await service.get_project(project_id=project_id, tenant_id=tenant_id)
    base = _build_project_response(project)
    template = LABELING_TEMPLATES.get(project.annotation_type)
    detail = AnnotationProjectDetailResponse(
        **base.model_dump(),
        label_config=project.label_config,
        labeling_template_description=template["description"] if template else None,
    )
    return BaseResponse(data=detail, message="获取成功")


@router.delete("/projects/{project_id}", response_model=BaseResponse[None])
async def delete_project(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    await service.delete_project(
        project_id=project_id,
        tenant_id=tenant_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message="标注项目删除成功")


def _build_task_response(task: Any, project: Any | None = None, assignee: Any | None = None) -> AnnotationTaskResponse:
    return AnnotationTaskResponse(
        id=task.id,
        project_id=task.project_id,
        label_studio_task_id=task.label_studio_task_id,
        data=task.data,
        assigned_to=task.assigned_to,
        assigned_to_name=assignee.username if assignee else None,
        status=task.status,
        project_name=project.name if project else None,
        annotation_type=project.annotation_type if project else None,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/projects/{project_id}/tasks", response_model=PageResponse[AnnotationTaskResponse])
async def list_project_tasks(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = _status_query,
    assigned_to: uuid.UUID | None = _assigned_to_query,
) -> PageResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    tasks, total = await service.list_project_tasks(
        project_id=project_id,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        assigned_to=assigned_to,
    )
    task_list = [_build_task_response(t, t.project, t.assignee) for t in tasks]
    page_data = PageData(items=task_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.post("/projects/{project_id}/assign", response_model=BaseResponse[None])
async def assign_tasks(
    project_id: uuid.UUID,
    req: AnnotationTaskAssignRequest,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    count = await service.assign_tasks(
        project_id=project_id,
        tenant_id=tenant_id,
        request=req,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message=f"成功分配 {count} 个任务")


@router.post("/projects/{project_id}/batch-assign", response_model=BaseResponse[None])
async def batch_assign_tasks(
    project_id: uuid.UUID,
    req: AnnotationBatchAssignRequest,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
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
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    tasks, total = await service.list_my_tasks(
        tenant_id=tenant_id,
        user_id=user.id,
        page=page,
        page_size=page_size,
    )
    task_list = [_build_task_response(t, t.project, t.assignee) for t in tasks]
    page_data = PageData(items=task_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/my-tasks/summary", response_model=BaseResponse[list[AnnotationTaskSummaryResponse]])
async def get_my_task_summary(
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
) -> BaseResponse[list[AnnotationTaskSummaryResponse]]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    rows = await service.get_my_task_summary(tenant_id=tenant_id, user_id=user.id)
    summary_list = [AnnotationTaskSummaryResponse(**row) for row in rows]
    return BaseResponse(data=summary_list, message="获取成功")


@router.post("/tasks/{task_id}/start", response_model=BaseResponse[AnnotationTaskResponse])
async def start_annotation(
    task_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "write"))],
) -> BaseResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    task = await service.start_annotation(
        task_id=task_id,
        tenant_id=tenant_id,
        user_id=user.id,
    )
    return BaseResponse(data=_build_task_response(task, task.project, task.assignee), message="开始标注")


@router.post("/tasks/{task_id}/submit", response_model=BaseResponse[AnnotationTaskResponse])
async def submit_annotation(
    task_id: uuid.UUID,
    req: AnnotationSubmitRequest,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "write"))],
) -> BaseResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    task = await service.submit_annotation(
        task_id=task_id,
        tenant_id=tenant_id,
        user_id=user.id,
        result=req.result,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=_build_task_response(task, task.project, task.assignee), message="标注提交成功")


@router.get("/projects/{project_id}/next-task", response_model=BaseResponse[AnnotationTaskResponse | None])
async def get_next_annotation_task(
    project_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "write"))],
) -> BaseResponse[AnnotationTaskResponse | None]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    task = await service.get_next_task(
        project_id=project_id,
        tenant_id=tenant_id,
        user_id=user.id,
    )
    if task is None:
        return BaseResponse(data=None, message="没有更多待标注任务")
    return BaseResponse(data=_build_task_response(task, task.project, task.assignee), message="获取成功")


@router.get("/tasks/{task_id}", response_model=BaseResponse[AnnotationTaskResponse])
async def get_annotation_task_detail(
    task_id: uuid.UUID,
    db: DbDep,
    ls: LabelStudioDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotations", "read"))],
) -> BaseResponse[AnnotationTaskResponse]:
    tenant_id = _require_tenant_id(user)
    service = AnnotationService(db, ls, minio)
    task = await service.get_task_detail(
        task_id=task_id,
        tenant_id=tenant_id,
    )
    return BaseResponse(data=_build_task_response(task, task.project, task.assignee), message="获取成功")
