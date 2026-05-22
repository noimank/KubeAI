import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.dev_environment_image import (
    DevEnvironmentImageCreateRequest,
    DevEnvironmentImageResponse,
    DevEnvironmentImageSelectableResponse,
    DevEnvironmentImageUpdateRequest,
)
from app.services.dev_environment_image_service import DevEnvironmentImageService

router = APIRouter(prefix="/dev-environment-images", tags=["dev-environment-images"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _audit_ctx(request: Request, user: Any) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


@router.get("", response_model=PageResponse[DevEnvironmentImageResponse])
async def list_dev_environment_images(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environment_images", "read"))],
    keyword: str | None = Query(None),
    environment_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[DevEnvironmentImageResponse]:
    service = DevEnvironmentImageService(db)
    tenant_id = getattr(user, "tenant_id", None)
    items, total = await service.list_images(
        keyword=keyword,
        environment_type=environment_type,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
    )
    data = [DevEnvironmentImageResponse.model_validate(img) for img in items]
    page_data = PageData(items=data, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/selectable", response_model=BaseResponse[list[DevEnvironmentImageSelectableResponse]])
async def list_selectable_dev_environment_images(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environment_images", "read"))],
) -> BaseResponse[list[DevEnvironmentImageSelectableResponse]]:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        from app.core.exceptions import ForbiddenException

        raise ForbiddenException("需要租户上下文")
    service = DevEnvironmentImageService(db)
    images = await service.list_selectable_images(tenant_id)
    data = [DevEnvironmentImageSelectableResponse.model_validate(img) for img in images]
    return BaseResponse(data=data, message="获取成功")


@router.get("/{image_id}", response_model=BaseResponse[DevEnvironmentImageResponse])
async def get_dev_environment_image(
    image_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environment_images", "read"))],
) -> BaseResponse[DevEnvironmentImageResponse]:
    service = DevEnvironmentImageService(db)
    img = await service.get_image(image_id)
    return BaseResponse(data=DevEnvironmentImageResponse.model_validate(img), message="获取成功")


@router.post("", response_model=BaseResponse[DevEnvironmentImageResponse])
async def create_dev_environment_image(
    req: DevEnvironmentImageCreateRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environment_images", "manage"))],
) -> BaseResponse[DevEnvironmentImageResponse]:
    service = DevEnvironmentImageService(db)
    tenant_id = getattr(user, "tenant_id", None)
    img = await service.create_image(
        name=req.name,
        environment_type=req.environment_type,
        image_ref=req.image_ref,
        description=req.description,
        icon=req.icon,
        default_cpu=req.default_cpu,
        default_memory=req.default_memory,
        default_gpu_count=req.default_gpu_count,
        tenant_id=tenant_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=DevEnvironmentImageResponse.model_validate(img), message="开发环境镜像创建成功")


@router.put("/{image_id}", response_model=BaseResponse[DevEnvironmentImageResponse])
async def update_dev_environment_image(
    image_id: uuid.UUID,
    req: DevEnvironmentImageUpdateRequest,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environment_images", "manage"))],
) -> BaseResponse[DevEnvironmentImageResponse]:
    service = DevEnvironmentImageService(db)
    update_data = req.model_dump(exclude_unset=True)
    img = await service.update_image(
        image_id=image_id,
        audit_context=_audit_ctx(request, user),
        **update_data,
    )
    return BaseResponse(data=DevEnvironmentImageResponse.model_validate(img), message="开发环境镜像更新成功")


@router.delete("/{image_id}", response_model=BaseResponse[None])
async def delete_dev_environment_image(
    image_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environment_images", "manage"))],
) -> BaseResponse[None]:
    service = DevEnvironmentImageService(db)
    await service.delete_image(
        image_id=image_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message="开发环境镜像删除成功")


@router.patch("/{image_id}/toggle", response_model=BaseResponse[DevEnvironmentImageResponse])
async def toggle_dev_environment_image(
    image_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environment_images", "manage"))],
) -> BaseResponse[DevEnvironmentImageResponse]:
    service = DevEnvironmentImageService(db)
    img = await service.toggle_image(
        image_id=image_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=DevEnvironmentImageResponse.model_validate(img), message="开发环境镜像状态切换成功")
