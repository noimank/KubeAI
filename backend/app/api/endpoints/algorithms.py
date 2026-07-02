import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import AppException
from app.models.algorithm import Algorithm
from app.models.enums import AuditAction, ResourceType, UserRole
from app.models.user import User
from app.schemas.algorithm import (
    AlgorithmDetailResponse,
    AlgorithmResponse,
    AlgorithmUpdateRequest,
    AlgorithmUploaderResponse,
)
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.dev_environment import DevEnvironmentCreateRequest, DevEnvironmentResponse
from app.services.algorithm_service import AlgorithmService
from app.services.algorithm_storage_service import AlgorithmStorageService
from app.services.audit_service import AuditService
from app.services.dev_environment_service import DevEnvironmentService
from app.tasks.dev_environment_tasks import enqueue_dev_environment_provision

router = APIRouter(prefix="/algorithms", tags=["algorithms"])

DbDep = Annotated[AsyncSession, Depends(get_db)]


def _require_tenant_id(user: Any) -> uuid.UUID:
    if user.tenant_id is None:
        raise AppException("请先加入租户", status_code=403)
    return uuid.UUID(str(user.tenant_id))


def _audit_ctx(request: Request, user: Any) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


def _can_manage_algorithms(user: Any) -> bool:
    """Return True if the user is admin or mlops (has algorithms:manage)."""
    return user.role in (UserRole.ADMIN, UserRole.MLOPS)


async def _resolve_uploader(db: AsyncSession, user_id: uuid.UUID) -> AlgorithmUploaderResponse:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return AlgorithmUploaderResponse(id=user_id, username="unknown")
    return AlgorithmUploaderResponse(
        id=user.id,
        username=user.username,
    )


async def _build_response(db: AsyncSession, algo: Algorithm) -> AlgorithmResponse:
    uploader = await _resolve_uploader(db, algo.user_id)
    return AlgorithmResponse(
        id=algo.id,
        name=algo.name,
        description=algo.description,
        tags=algo.tags,
        source_type=algo.source_type,
        size_bytes=algo.size_bytes,
        status=algo.status,
        visibility=algo.visibility,
        uploader=uploader,
        created_at=algo.created_at,
        updated_at=algo.updated_at,
    )


async def _build_detail_response(db: AsyncSession, algo: Algorithm) -> AlgorithmDetailResponse:
    base = await _build_response(db, algo)
    return AlgorithmDetailResponse(
        **base.model_dump(),
        storage_path=algo.storage_path,
    )


# ------------------------------------------------------------------
# POST /
# ------------------------------------------------------------------
@router.post("", response_model=BaseResponse[AlgorithmDetailResponse])
async def create_algorithm(
    req: Request,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("algorithms", "write"))],
    name: str = Query(..., min_length=1, max_length=200),
    description: str | None = Query(None),
    tags: str | None = Query(None),
    file: UploadFile | None = None,
) -> BaseResponse[AlgorithmDetailResponse]:
    if file is None:
        raise AppException("请选择算法文件", status_code=400)
    tenant_id = _require_tenant_id(user)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    file_bytes = await file.read()
    filename = file.filename or "algorithm"

    service = AlgorithmService(db)
    algo = await service.create_algorithm(
        tenant_id=tenant_id,
        user_id=user.id,
        name=name,
        description=description,
        tags=tag_list,
        file_bytes=file_bytes,
        filename=filename,
        audit_context=_audit_ctx(req, user),
    )
    data = await _build_detail_response(db, algo)
    return BaseResponse(data=data, message="算法上传成功")


# ------------------------------------------------------------------
# GET /
# ------------------------------------------------------------------
@router.get("", response_model=PageResponse[AlgorithmResponse])
async def list_algorithms(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("algorithms", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    name: str | None = Query(None),
    tag: str | None = Query(None),
    uploader: str | None = Query(None),
) -> PageResponse[AlgorithmResponse]:
    tenant_id = _require_tenant_id(user)
    service = AlgorithmService(db)

    uploader_id: uuid.UUID | None = None
    if uploader:
        try:
            uploader_id = uuid.UUID(uploader)
        except ValueError:
            raise AppException("上传者 ID 格式无效", status_code=400) from None

    items, total = await service.list_algorithms(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        name=name,
        tag=tag,
        uploader_id=uploader_id,
    )

    data_list = [await _build_response(db, a) for a in items]
    page_data = PageData(items=data_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


# ------------------------------------------------------------------
# GET /{id}
# ------------------------------------------------------------------
@router.get("/{algorithm_id}", response_model=BaseResponse[AlgorithmDetailResponse])
async def get_algorithm(
    algorithm_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("algorithms", "read"))],
) -> BaseResponse[AlgorithmDetailResponse]:
    tenant_id = _require_tenant_id(user)
    service = AlgorithmService(db)
    algo = await service.get_algorithm(algorithm_id, tenant_id)
    data = await _build_detail_response(db, algo)
    return BaseResponse(data=data, message="获取成功")


# ------------------------------------------------------------------
# GET /{id}/download
# ------------------------------------------------------------------
@router.get("/{algorithm_id}/download")
async def download_algorithm(
    algorithm_id: uuid.UUID,
    req: Request,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("algorithms", "read"))],
) -> FileResponse:
    tenant_id = _require_tenant_id(user)
    service = AlgorithmService(db)
    algo = await service.get_algorithm(algorithm_id, tenant_id)

    tenant_name = await service._get_tenant_name(tenant_id)
    storage = AlgorithmStorageService(tenant_name)
    file_path = storage.get_file_path(algo.user_id, algorithm_id)

    if not file_path.exists():
        raise AppException("算法文件不存在", status_code=404)

    # Audit log for download
    audit_svc = AuditService(db)
    ctx = _audit_ctx(req, user)
    await audit_svc.log_action(
        action=AuditAction.DOWNLOAD,
        resource_type=ResourceType.ALGORITHM,
        resource_id=str(algorithm_id),
        detail={"name": algo.name},
        tenant_id=tenant_id,
        **ctx,
    )

    return FileResponse(
        path=str(file_path),
        filename=f"{algo.name}.zip",
        media_type="application/zip",
    )


# ------------------------------------------------------------------
# PATCH /{id}
# ------------------------------------------------------------------
@router.patch("/{algorithm_id}", response_model=BaseResponse[AlgorithmResponse])
async def update_algorithm(
    algorithm_id: uuid.UUID,
    req: AlgorithmUpdateRequest,
    request: Request,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("algorithms", "write"))],
) -> BaseResponse[AlgorithmResponse]:
    tenant_id = _require_tenant_id(user)
    is_admin = _can_manage_algorithms(user)

    if req.name is None and req.description is None and req.tags is None:
        raise AppException("至少需要传入一个可编辑字段", status_code=400)

    service = AlgorithmService(db)
    algo = await service.update_algorithm(
        algorithm_id=algorithm_id,
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        description=req.description,
        tags=req.tags,
        is_admin=is_admin,
        audit_context=_audit_ctx(request, user),
    )
    data = await _build_response(db, algo)
    return BaseResponse(data=data, message="算法更新成功")


# ------------------------------------------------------------------
# DELETE /{id}
# ------------------------------------------------------------------
@router.delete("/{algorithm_id}", response_model=BaseResponse[None])
async def delete_algorithm(
    algorithm_id: uuid.UUID,
    request: Request,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("algorithms", "write"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    is_admin = _can_manage_algorithms(user)

    service = AlgorithmService(db)
    await service.delete_algorithm(
        algorithm_id=algorithm_id,
        tenant_id=tenant_id,
        user_id=user.id,
        is_admin=is_admin,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(data=None, message="算法删除成功")


# ------------------------------------------------------------------
# POST /{id}/dev-environment
# ------------------------------------------------------------------
@router.post("/{algorithm_id}/dev-environment", response_model=BaseResponse[DevEnvironmentResponse])
async def create_dev_environment_from_algorithm(
    algorithm_id: uuid.UUID,
    req: DevEnvironmentCreateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "write"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)

    # Verify algorithm exists and user can access it
    algo_service = AlgorithmService(db)
    await algo_service.get_algorithm(algorithm_id, tenant_id)

    # Set the algorithm_id into the request (override any user-supplied value)
    req.algorithm_id = algorithm_id

    env_service = DevEnvironmentService(db)
    env = await env_service.create_environment(
        tenant_id=tenant_id,
        user_id=user.id,
        username=user.username,
        name=req.name,
        environment_image_id=req.environment_image_id,
        gpu_count=req.gpu_count,
        cpu=req.cpu,
        memory=req.memory,
        description=req.description,
        env_vars=req.env_vars,
        datasets=req.datasets,
    )
    await enqueue_dev_environment_provision(env.id, tenant_id, req.algorithm_id)
    return BaseResponse(data=DevEnvironmentResponse.model_validate(env), message="开发环境创建任务已提交")
