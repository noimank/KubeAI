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
    AnnotationProjectCreateRequest,
    AnnotationProjectDetailResponse,
    AnnotationProjectResponse,
    AnnotationTemplateResponse,
)
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.services.annotation_service import AnnotationService

router = APIRouter(prefix="/annotations", tags=["annotations"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
MinioDep = Annotated[MinIOClient, Depends(lambda: get_minio_client())]
LabelStudioDep = Annotated[LabelStudioClient, Depends(lambda: get_labelstudio_client())]
_keyword_query = Query(None)


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
