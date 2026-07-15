import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import AppException
from app.models.annotation import AnnotationProject
from app.models.annotation_template import AnnotationTemplate
from app.schemas.annotation_template import (
    AnnotationTemplateCreateRequest,
    AnnotationTemplateDetailResponse,
    AnnotationTemplateImportItem,
    AnnotationTemplateResponse,
    AnnotationTemplateUpdateRequest,
)
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.services.annotation_template_service import AnnotationTemplateService

router = APIRouter(prefix="/annotation-templates", tags=["annotation-templates"])
DbDep = Annotated[AsyncSession, Depends(get_db)]


def _audit_ctx(request: Request, user: Any) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


def _require_tenant_id(user: Any) -> uuid.UUID:
    if user.tenant_id is None:
        raise AppException("请先加入租户", status_code=403)
    return uuid.UUID(str(user.tenant_id))


async def _resolve_project_count(db: AsyncSession, template_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not template_ids:
        return {}
    rows = await db.execute(
        select(AnnotationProject.template_id, func.count())
        .where(AnnotationProject.template_id.in_(template_ids))
        .group_by(AnnotationProject.template_id)
    )
    return {tid: cnt for tid, cnt in rows.all()}


def _to_response(tpl: AnnotationTemplate) -> AnnotationTemplateResponse:
    return AnnotationTemplateResponse(
        id=tpl.id,
        name=tpl.name,
        description=tpl.description,
        tags=tpl.tags,
        group=tpl.group,
        created_by=tpl.user_id,
        created_at=tpl.created_at,
        updated_at=tpl.updated_at,
    )


def _to_detail(tpl: AnnotationTemplate, project_count: int = 0) -> AnnotationTemplateDetailResponse:
    base = _to_response(tpl)
    return AnnotationTemplateDetailResponse(
        **base.model_dump(),
        label_config=tpl.label_config,
        project_count=project_count,
    )


# ------------------------------------------------------------------
# GET /ls-imports  (内置模板市场 — 从静态 JSON 文件读取)
# ------------------------------------------------------------------
@router.get(
    "/ls-imports",
    response_model=BaseResponse[list[AnnotationTemplateImportItem]],
)
async def list_builtin_marketplace_templates(
    user: Annotated[CurrentUser, Depends(require_permission("annotation_templates", "read"))],
) -> BaseResponse[list[AnnotationTemplateImportItem]]:
    import json
    from pathlib import Path

    builtin_path = (
        Path(__file__).resolve().parent.parent.parent / "integrations" / "labelstudio" / "builtin_templates.json"
    )
    with builtin_path.open(encoding="utf-8") as f:
        raw = json.load(f)
    items = [AnnotationTemplateImportItem(**item) for item in raw]
    return BaseResponse(data=items, message="获取成功")


# ------------------------------------------------------------------
# POST /
# ------------------------------------------------------------------
@router.post("", response_model=BaseResponse[AnnotationTemplateDetailResponse])
async def create_template(
    req: AnnotationTemplateCreateRequest,
    request: Request,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotation_templates", "write"))],
) -> BaseResponse[AnnotationTemplateDetailResponse]:
    tenant_id = _require_tenant_id(user)
    svc = AnnotationTemplateService(db)
    tpl = await svc.create_template(
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        description=req.description,
        label_config=req.label_config,
        tags=req.tags,
        group=req.group,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=_to_detail(tpl, 0), message="模板创建成功")


# ------------------------------------------------------------------
# GET /groups
# ------------------------------------------------------------------
@router.get("/groups", response_model=BaseResponse[list[str]])
async def list_groups(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotation_templates", "read"))],
) -> BaseResponse[list[str]]:
    tenant_id = _require_tenant_id(user)
    svc = AnnotationTemplateService(db)
    groups = await svc.get_groups(tenant_id)
    return BaseResponse(data=groups, message="获取成功")


# ------------------------------------------------------------------
# GET /
# ------------------------------------------------------------------
@router.get("", response_model=PageResponse[AnnotationTemplateResponse])
async def list_templates(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotation_templates", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    name: str | None = Query(None),
    tag: str | None = Query(None),
    group: str | None = Query(None),
) -> PageResponse[AnnotationTemplateResponse]:
    tenant_id = _require_tenant_id(user)
    svc = AnnotationTemplateService(db)
    items, total = await svc.list_templates(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        name=name,
        tag=tag,
        group=group,
    )
    data = [_to_response(t) for t in items]
    return PageResponse(
        data=PageData(items=data, total=total, page=page, page_size=page_size),
        message="获取成功",
    )


# ------------------------------------------------------------------
# GET /{id}
# ------------------------------------------------------------------
@router.get("/{template_id}", response_model=BaseResponse[AnnotationTemplateDetailResponse])
async def get_template(
    template_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotation_templates", "read"))],
) -> BaseResponse[AnnotationTemplateDetailResponse]:
    tenant_id = _require_tenant_id(user)
    svc = AnnotationTemplateService(db)
    tpl = await svc.get_template(template_id, tenant_id)
    counts = await _resolve_project_count(db, [tpl.id])
    return BaseResponse(data=_to_detail(tpl, counts.get(tpl.id, 0)), message="获取成功")


# ------------------------------------------------------------------
# PATCH /{id}
# ------------------------------------------------------------------
@router.patch("/{template_id}", response_model=BaseResponse[AnnotationTemplateResponse])
async def update_template(
    template_id: uuid.UUID,
    req: AnnotationTemplateUpdateRequest,
    request: Request,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotation_templates", "write"))],
) -> BaseResponse[AnnotationTemplateResponse]:
    tenant_id = _require_tenant_id(user)
    svc = AnnotationTemplateService(db)
    tpl = await svc.update_template(
        template_id=template_id,
        tenant_id=tenant_id,
        name=req.name,
        description=req.description,
        label_config=req.label_config,
        tags=req.tags,
        group=req.group,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=_to_response(tpl), message="模板更新成功")


# ------------------------------------------------------------------
# DELETE /{id}
# ------------------------------------------------------------------
@router.delete("/{template_id}", response_model=BaseResponse[None])
async def delete_template(
    template_id: uuid.UUID,
    request: Request,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("annotation_templates", "write"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    svc = AnnotationTemplateService(db)
    await svc.delete_template(
        template_id=template_id,
        tenant_id=tenant_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=None, message="模板删除成功")
