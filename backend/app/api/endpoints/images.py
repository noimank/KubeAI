import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.models.image import Image
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.image import (
    ImageBuildLogResponse,
    ImageBuildRequest,
    ImageCreateRequest,
    ImageResponse,
    ImageUpdateRequest,
)
from app.services.image_service import ImageService

router = APIRouter(prefix="/images", tags=["images"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
_keyword_query = Query(None)
_source_query = Query(None)


def _audit_ctx(request: Request, user: Any) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


async def _require_tenant_id(user: Any) -> uuid.UUID:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        from app.core.exceptions import ForbiddenException

        raise ForbiddenException("需要租户上下文才能操作自定义镜像")
    return tenant_id


def _to_response(img: Image) -> ImageResponse:
    from app.models.enums import BuildStatus

    build_status = BuildStatus(img.build_status) if img.build_status else None
    return ImageResponse(
        id=img.id,
        name=img.name,
        tag=img.tag,
        image_ref=img.image_ref,
        description=img.description,
        source=img.source,
        is_enabled=img.is_enabled,
        tenant_id=img.tenant_id,
        build_status=build_status,
        dockerfile=img.dockerfile,
        created_at=img.created_at,
        updated_at=img.updated_at,
    )


@router.get("", response_model=PageResponse[ImageResponse])
async def list_images(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("images", "read"))],
    keyword: str | None = _keyword_query,
    source: str | None = _source_query,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[ImageResponse]:
    service = ImageService(db)
    tenant_id = getattr(user, "tenant_id", None)
    items, total = await service.list_images(
        keyword=keyword,
        source=source,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
    )
    image_list = [_to_response(img) for img in items]
    page_data = PageData(items=image_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{image_id}", response_model=BaseResponse[ImageResponse])
async def get_image(
    image_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("images", "read"))],
) -> BaseResponse[ImageResponse]:
    service = ImageService(db)
    image = await service.get_image(image_id)
    image = await service.sync_build_status(image)
    return BaseResponse(data=_to_response(image), message="获取成功")


@router.post("", response_model=BaseResponse[ImageResponse])
async def create_image(
    req: ImageCreateRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("images", "manage"))],
) -> BaseResponse[ImageResponse]:
    service = ImageService(db)
    image = await service.create_image(
        name=req.name,
        tag=req.tag,
        image_ref=req.image_ref,
        description=req.description,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=_to_response(image), message="镜像创建成功")


@router.post("/build", response_model=BaseResponse[ImageResponse])
async def build_image(
    req: ImageBuildRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("images", "build"))],
) -> BaseResponse[ImageResponse]:
    tenant_id = await _require_tenant_id(user)
    service = ImageService(db)
    image = await service.build_image(
        dockerfile=req.dockerfile,
        name=req.name,
        tag=req.tag,
        description=req.description,
        tenant_id=tenant_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=_to_response(image), message="构建任务已提交")


@router.get("/{image_id}/build-log", response_model=BaseResponse[ImageBuildLogResponse])
async def get_build_log(
    image_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("images", "read"))],
) -> BaseResponse[ImageBuildLogResponse]:
    service = ImageService(db)
    image = await service.get_image(image_id)
    image = await service.sync_build_status(image)
    log = await service.get_build_log(image_id)
    from app.models.enums import BuildStatus

    build_status = BuildStatus(image.build_status) if image.build_status else None
    return BaseResponse(
        data=ImageBuildLogResponse(build_status=build_status, log=log),
        message="获取成功",
    )


@router.post("/{image_id}/rebuild", response_model=BaseResponse[ImageResponse])
async def rebuild_image(
    image_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("images", "build"))],
) -> BaseResponse[ImageResponse]:
    service = ImageService(db)
    image = await service.rebuild_image(
        image_id=image_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=_to_response(image), message="重新构建已提交")


@router.put("/{image_id}", response_model=BaseResponse[ImageResponse])
async def update_image(
    image_id: uuid.UUID,
    req: ImageUpdateRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("images", "manage"))],
) -> BaseResponse[ImageResponse]:
    service = ImageService(db)
    update_data = req.model_dump(exclude_unset=True)
    image = await service.update_image(
        image_id=image_id,
        audit_context=_audit_ctx(request, user),
        **update_data,
    )
    return BaseResponse(data=_to_response(image), message="镜像更新成功")


@router.delete("/{image_id}", response_model=BaseResponse[None])
async def delete_image(
    image_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("images", "manage"))],
) -> BaseResponse[None]:
    service = ImageService(db)
    await service.delete_image(
        image_id=image_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message="镜像删除成功")


@router.patch("/{image_id}/toggle", response_model=BaseResponse[ImageResponse])
async def toggle_image(
    image_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("images", "manage"))],
) -> BaseResponse[ImageResponse]:
    service = ImageService(db)
    image = await service.toggle_image(
        image_id=image_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=_to_response(image), message="镜像状态切换成功")
