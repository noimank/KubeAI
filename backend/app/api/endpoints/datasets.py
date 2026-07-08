import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, QueryOrHeaderUser, get_db, require_permission
from app.core.exceptions import NotFoundException
from app.models.dataset import Dataset
from app.models.user import User
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.dataset import (
    DatasetCreateRequest,
    DatasetDetailResponse,
    DatasetResponse,
    DatasetVersionCreateRequest,
    DatasetVersionResponse,
    FileDownloadRequest,
    SortBy,
    SortDir,
    VersionFileResponse,
    VersionStatsResponse,
)
from app.services.dataset_service import DatasetService

router = APIRouter(prefix="/datasets", tags=["datasets"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
_files_default = File(...)
_keyword_query = Query(None)
_start_date_query = Query(None)
_end_date_query = Query(None)


def _audit_ctx(request: Request, user: Any) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


def _build_dataset_response(
    dataset: Dataset,
    user_name_map: dict[uuid.UUID, str] | None = None,
) -> DatasetResponse:
    versions = sorted(dataset.versions, key=lambda v: v.version_number)
    latest = versions[-1] if versions else None
    total_file_count = sum(v.file_count for v in versions)
    total_size_bytes = sum(v.total_size_bytes for v in versions)
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        display_name=dataset.display_name,
        description=dataset.description,
        tenant_id=dataset.tenant_id,
        created_by=dataset.created_by,
        created_by_name=(user_name_map or {}).get(dataset.created_by),
        version_count=len(versions),
        total_file_count=total_file_count,
        total_size_bytes=total_size_bytes,
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
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "write"))],
) -> BaseResponse[DatasetResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    dataset = await service.create_dataset(
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        display_name=req.display_name,
        description=req.description,
        audit_context=_audit_ctx(request, user),
    )
    await db.refresh(dataset)
    return BaseResponse(data=_build_dataset_response(dataset), message="数据集创建成功")


@router.get("", response_model=PageResponse[DatasetResponse])
async def list_datasets(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str | None = _keyword_query,
    start_date: date | None = _start_date_query,
    end_date: date | None = _end_date_query,
) -> PageResponse[DatasetResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    items, total = await service.list_datasets(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
    )
    user_name_map = await _resolve_user_names(db, items)
    dataset_list = [_build_dataset_response(ds, user_name_map) for ds in items]
    page_data = PageData(items=dataset_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{dataset_id}", response_model=BaseResponse[DatasetDetailResponse])
async def get_dataset(
    dataset_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "read"))],
) -> BaseResponse[DatasetDetailResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    dataset = await service.get_dataset(dataset_id=dataset_id, tenant_id=tenant_id)
    user_name_map = await _resolve_user_names(db, [dataset])
    base = _build_dataset_response(dataset, user_name_map)
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
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "write"))],
) -> BaseResponse[DatasetVersionResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
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


@router.post(
    "/{dataset_id}/versions/{version_id}/upload",
    response_model=BaseResponse[list[VersionFileResponse]],
)
async def upload_files(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "write"))],
    files: list[UploadFile] = _files_default,
) -> BaseResponse[list[VersionFileResponse]]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    rows = await service.upload_files_to_version(
        tenant_id=tenant_id,
        dataset_id=dataset_id,
        version_id=version_id,
        files=files,
        user_id=user.id,
    )
    data = [VersionFileResponse.from_orm_file(r) for r in rows]
    return BaseResponse(data=data, message="文件上传成功")


@router.delete("/{dataset_id}/versions/{version_id}", response_model=BaseResponse[None])
async def delete_version(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    await service.delete_version(
        dataset_id=dataset_id,
        version_id=version_id,
        tenant_id=tenant_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message="版本删除成功")


@router.delete("/{dataset_id}", response_model=BaseResponse[None])
async def delete_dataset(
    dataset_id: uuid.UUID,
    db: DbDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "manage"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    await service.delete_dataset(
        dataset_id=dataset_id,
        tenant_id=tenant_id,
        audit_context=_audit_ctx(request, user),
    )
    return BaseResponse(message="数据集删除成功")


@router.get(
    "/{dataset_id}/versions/{version_id}/files",
    response_model=PageResponse[VersionFileResponse],
)
async def list_version_files(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    sort_by: SortBy = "file_name",
    sort_dir: SortDir = "asc",
) -> PageResponse[VersionFileResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    rows, total, annotated = await service.list_version_files(
        dataset_id=dataset_id,
        version_id=version_id,
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    page_data = PageData(
        items=[VersionFileResponse.from_orm_file(r, is_annotated=r.file_name in annotated) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
    return PageResponse(data=page_data, message="查询成功")


@router.get(
    "/{dataset_id}/versions/{version_id}/stats",
    response_model=BaseResponse[VersionStatsResponse],
)
async def get_version_stats(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "read"))],
) -> BaseResponse[VersionStatsResponse]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    stats = await service.get_version_stats(dataset_id, version_id, tenant_id)
    data = VersionStatsResponse(**stats)
    return BaseResponse(data=data, message="查询成功")


@router.post(
    "/{dataset_id}/versions/{version_id}/files/download-url",
    response_model=BaseResponse[str],
)
async def get_file_download_url(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    body: FileDownloadRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "read"))],
) -> BaseResponse[str]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    url = await service.get_file_download_url(dataset_id, version_id, body.file_name, tenant_id)
    return BaseResponse(data=url, message="获取成功")


@router.get("/{dataset_id}/versions/{version_id}/files/{file_name:path}/download")
async def download_file(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    file_name: str,
    db: DbDep,
    user: QueryOrHeaderUser,
) -> FileResponse:
    """Download a dataset file. Supports both Bearer header and ?token= query parameter auth."""
    from app.core.casbin import CasbinEnforcer
    from app.core.exceptions import ForbiddenException as ForbiddenExc

    if not CasbinEnforcer.enforce(user.role.value, "datasets", "read"):
        raise ForbiddenExc("权限不足: 无法对 datasets 执行 read 操作")
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    file_path = await service.get_file_path(dataset_id, version_id, file_name, tenant_id)
    if not file_path.exists():
        from app.core.exceptions import NotFoundException

        raise NotFoundException("文件不存在")
    return FileResponse(path=str(file_path), filename=file_name)


@router.get(
    "/{dataset_id}/versions/{version_id}/files/{file_name:path}/annotation",
    response_model=BaseResponse[dict[str, Any]],
)
async def get_file_annotation(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    file_name: str,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "read"))],
) -> BaseResponse[dict[str, Any]]:
    """Read the per-file annotation JSON for a dataset file (404 if absent)."""
    import json as _json
    from pathlib import Path

    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    annotation_filename = Path(file_name).name + ".json"
    annotation_path = await service.get_file_path(
        dataset_id, version_id, f"annotations/{annotation_filename}", tenant_id
    )
    if not annotation_path.exists():
        raise NotFoundException("该文件暂无标注")
    content = await service.storage.get_file_content(annotation_path)
    return BaseResponse(data=_json.loads(content.decode("utf-8")), message="获取成功")


@router.delete(
    "/{dataset_id}/versions/{version_id}/files/{file_id}",
    response_model=BaseResponse[None],
)
async def delete_file(
    dataset_id: uuid.UUID,
    version_id: uuid.UUID,
    file_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("datasets", "write"))],
) -> BaseResponse[None]:
    tenant_id = _require_tenant_id(user)
    service = DatasetService(db)
    await service.delete_file(dataset_id, version_id, file_id, tenant_id)
    return BaseResponse(message="文件删除成功")


def _require_tenant_id(user: Any) -> uuid.UUID:
    if user.tenant_id is None:
        from app.core.exceptions import ForbiddenException

        raise ForbiddenException("请先加入租户")
    return uuid.UUID(str(user.tenant_id))


async def _resolve_user_names(db: AsyncSession, datasets: list[Dataset]) -> dict[uuid.UUID, str]:
    user_ids = {ds.created_by for ds in datasets}
    if not user_ids:
        return {}
    result = await db.execute(select(User.id, User.username).where(User.id.in_(user_ids)))
    return {row.id: row.username for row in result.all()}
