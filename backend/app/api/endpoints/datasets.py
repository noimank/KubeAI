import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.events import get_minio_client
from app.integrations.minio import MinIOClient
from app.models.dataset import Dataset
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.dataset import (
    DatasetCreateRequest,
    DatasetDetailResponse,
    DatasetResponse,
    DatasetVersionCreateRequest,
    DatasetVersionResponse,
    FileUploadResponse,
)
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
MinioDep = Annotated[MinIOClient, Depends(lambda: get_minio_client())]
_files_default = File(...)


def _audit_ctx(request: Request, user: Any) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


def _build_dataset_response(dataset: Dataset) -> DatasetResponse:
    versions = sorted(dataset.versions, key=lambda v: v.version_number)
    latest = versions[-1] if versions else None
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        tenant_id=dataset.tenant_id,
        created_by=dataset.created_by,
        version_count=len(versions),
        latest_version=DatasetVersionResponse(
            id=latest.id,
            dataset_id=latest.dataset_id,
            version_number=latest.version_number,
            description=latest.description,
            storage_path=latest.storage_path,
            file_count=latest.file_count,
            total_size_bytes=latest.total_size_bytes,
            created_by=latest.created_by,
            created_at=latest.created_at,
        )
        if latest
        else None,
        created_at=dataset.created_at,
        updated_at=dataset.updated_at,
    )


@router.post("", response_model=BaseResponse[DatasetResponse])
async def create_dataset(
    req: DatasetCreateRequest,
    db: DbDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "write"))],
) -> BaseResponse[DatasetResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db, minio)
    dataset = await service.create_dataset(
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        description=req.description,
        audit_context=_audit_ctx(request, user),
    )
    await db.refresh(dataset)
    return BaseResponse(data=_build_dataset_response(dataset), message="数据集创建成功")


@router.get("", response_model=PageResponse[DatasetResponse])
async def list_datasets(
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = Query(None),
) -> PageResponse[DatasetResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db, minio)
    items, total = await service.list_datasets(tenant_id=tenant_id, page=page, page_size=page_size, keyword=keyword)
    dataset_list = [_build_dataset_response(ds) for ds in items]
    page_data = PageData(items=dataset_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{dataset_id}", response_model=BaseResponse[DatasetDetailResponse])
async def get_dataset(
    dataset_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "read"))],
) -> BaseResponse[DatasetDetailResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db, minio)
    dataset = await service.get_dataset(dataset_id=dataset_id, tenant_id=tenant_id)
    base = _build_dataset_response(dataset)
    versions = sorted(dataset.versions, key=lambda v: v.version_number)
    detail = DatasetDetailResponse(
        **base.model_dump(),
        versions=[
            DatasetVersionResponse(
                id=v.id,
                dataset_id=v.dataset_id,
                version_number=v.version_number,
                description=v.description,
                storage_path=v.storage_path,
                file_count=v.file_count,
                total_size_bytes=v.total_size_bytes,
                created_by=v.created_by,
                created_at=v.created_at,
            )
            for v in versions
        ],
    )
    return BaseResponse(data=detail, message="获取成功")


@router.post("/{dataset_id}/versions", response_model=BaseResponse[DatasetVersionResponse])
async def create_version(
    dataset_id: uuid.UUID,
    req: DatasetVersionCreateRequest,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "write"))],
) -> BaseResponse[DatasetVersionResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db, minio)
    version = await service.create_version(
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        user_id=user.id,
        description=req.description,
    )
    data = DatasetVersionResponse(
        id=version.id,
        dataset_id=version.dataset_id,
        version_number=version.version_number,
        description=version.description,
        storage_path=version.storage_path,
        file_count=version.file_count,
        total_size_bytes=version.total_size_bytes,
        created_by=version.created_by,
        created_at=version.created_at,
    )
    return BaseResponse(data=data, message="版本创建成功")


@router.post("/{dataset_id}/versions/{version_id}/upload", response_model=BaseResponse[list[FileUploadResponse]])
async def upload_files(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "write"))],
    files: list[UploadFile] = _files_default,
) -> BaseResponse[list[FileUploadResponse]]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db, minio)
    results = await service.upload_files_to_version(
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        version_id=version_id,
        files=files,
    )
    data = [FileUploadResponse(**r) for r in results]
    return BaseResponse(data=data, message="文件上传成功")


@router.delete("/{dataset_id}", response_model=BaseResponse[None])
async def delete_dataset(
    dataset_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db, minio)
    await service.delete_dataset(
        dataset_id=dataset_id,
        tenant_id=tenant_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message="数据集删除成功")


def _require_tenant_id(user: Any) -> uuid.UUID:
    if user.tenant_id is None:
        from app.core.exceptions import ForbiddenException

        raise ForbiddenException("请先加入租户")
    return uuid.UUID(str(user.tenant_id))
