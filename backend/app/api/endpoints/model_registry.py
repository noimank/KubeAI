import io
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.config import settings
from app.core.events import get_minio_client
from app.core.exceptions import BadRequestException, NotFoundException
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.pvc import make_workspace_host_path
from app.integrations.k8s.upload_job import build_upload_job, create_upload_job, get_upload_job_status
from app.integrations.minio import MinIOClient
from app.models.dataset import Dataset, DatasetVersion
from app.models.enums import ModelVersionStatus
from app.models.image import Image
from app.models.registered_model import ModelVersion, RegisteredModel
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.models.user import User
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.model_registry import (
    ModelFileDownloadRequest,
    ModelVersionCreateRequest,
    ModelVersionFileResponse,
    ModelVersionResponse,
    RegisteredModelDetailResponse,
    RegisteredModelResponse,
)
from app.services.audit_service import AuditService

router = APIRouter(prefix="/model-registry", tags=["model-registry"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
MinioDep = Annotated[MinIOClient, Depends(lambda: get_minio_client())]


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


def _build_model_response(
    model: RegisteredModel,
    user_name_map: dict[uuid.UUID, str] | None = None,
    training_job_names: dict[uuid.UUID, str] | None = None,
    dataset_names: dict[uuid.UUID, str] | None = None,
    dataset_version_numbers: dict[uuid.UUID, int] | None = None,
    image_info: dict[uuid.UUID, tuple[str, str]] | None = None,
) -> RegisteredModelResponse:
    versions = sorted(model.versions, key=lambda v: v.version_number)
    latest = versions[-1] if versions else None
    _tjn = training_job_names or {}
    _dn = dataset_names or {}
    _dvn = dataset_version_numbers or {}
    _ii = image_info or {}
    return RegisteredModelResponse(
        id=model.id,
        name=model.name,
        description=model.description,
        tenant_id=model.tenant_id,
        created_by=model.created_by,
        created_by_name=(user_name_map or {}).get(model.created_by),
        version_count=len(versions),
        latest_version=(
            _build_version_response(
                latest,
                _tjn.get(latest.training_job_id) if latest and latest.training_job_id else None,
                _dn.get(latest.dataset_id) if latest and latest.dataset_id else None,
                _dvn.get(latest.dataset_version_id) if latest and latest.dataset_version_id else None,
                (_ii.get(latest.image_id) or (None, None))[0] if latest and latest.image_id else None,
                (_ii.get(latest.image_id) or (None, None))[1] if latest and latest.image_id else None,
            )
            if latest
            else None
        ),
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _build_version_response(
    v: ModelVersion,
    training_job_name: str | None = None,
    dataset_name: str | None = None,
    dataset_version_number: int | None = None,
    image_name: str | None = None,
    image_tag: str | None = None,
) -> ModelVersionResponse:
    return ModelVersionResponse(
        id=v.id,
        registered_model_id=v.registered_model_id,
        version_number=v.version_number,
        description=v.description,
        storage_path=v.storage_path,
        status=v.status,
        file_count=v.file_count,
        total_size_bytes=v.total_size_bytes,
        training_job_id=v.training_job_id,
        training_job_name=training_job_name,
        dataset_id=v.dataset_id,
        dataset_name=dataset_name,
        dataset_version_id=v.dataset_version_id,
        dataset_version_number=dataset_version_number,
        image_id=v.image_id,
        image_name=image_name,
        image_tag=image_tag,
        hyperparameters=v.hyperparameters,
        created_by=v.created_by,
        created_at=v.created_at,
    )


async def _resolve_user_names(db: AsyncSession, models: list[RegisteredModel]) -> dict[uuid.UUID, str]:
    user_ids = {m.created_by for m in models}
    if not user_ids:
        return {}
    result = await db.execute(select(User.id, User.username).where(User.id.in_(user_ids)))
    return {row.id: row.username for row in result.all()}


async def _resolve_training_job_names(db: AsyncSession, versions: list[ModelVersion]) -> dict[uuid.UUID, str]:
    job_ids = {v.training_job_id for v in versions if v.training_job_id}
    if not job_ids:
        return {}
    result = await db.execute(select(TrainingJob.id, TrainingJob.name).where(TrainingJob.id.in_(job_ids)))
    return {row.id: row.name for row in result.all()}


async def _resolve_dataset_info(
    db: AsyncSession, versions: list[ModelVersion]
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, int]]:
    dataset_ids = {v.dataset_id for v in versions if v.dataset_id}
    version_ids = {v.dataset_version_id for v in versions if v.dataset_version_id}

    dataset_names: dict[uuid.UUID, str] = {}
    version_numbers: dict[uuid.UUID, int] = {}

    if dataset_ids:
        result = await db.execute(select(Dataset.id, Dataset.name).where(Dataset.id.in_(dataset_ids)))
        dataset_names = {row.id: row.name for row in result.all()}

    if version_ids:
        result = await db.execute(
            select(DatasetVersion.id, DatasetVersion.version_number).where(DatasetVersion.id.in_(version_ids))
        )
        version_numbers = {row.id: row.version_number for row in result.all()}

    return dataset_names, version_numbers


async def _resolve_image_info(db: AsyncSession, versions: list[ModelVersion]) -> dict[uuid.UUID, tuple[str, str]]:
    image_ids = {v.image_id for v in versions if v.image_id}
    if not image_ids:
        return {}
    result = await db.execute(select(Image.id, Image.name, Image.tag).where(Image.id.in_(image_ids)))
    return {row.id: (row.name, row.tag) for row in result.all()}


async def _sync_version_upload_status(
    version: ModelVersion,
    db: AsyncSession,
    minio: MinIOClient,
    tenant: Tenant,
) -> None:
    if version.status != ModelVersionStatus.UPLOADING:
        return

    namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

    if version.upload_job_name:
        job_status = await get_upload_job_status(namespace, version.upload_job_name)
        k8s_status = job_status.get("status")

        if k8s_status == "completed":
            await _finalize_upload(version, db, minio, tenant)
            return
        if k8s_status == "failed":
            version.status = ModelVersionStatus.FAILED
            await db.flush()
            return

    # Job not found (TTL expired) or still running — check MinIO directly
    await _finalize_upload(version, db, minio, tenant)


async def _finalize_upload(
    version: ModelVersion,
    db: AsyncSession,
    minio: MinIOClient,
    tenant: Tenant,
) -> None:
    try:
        objects = await minio.list_objects(tenant.name, version.storage_path)
    except Exception:
        return

    if objects:
        version.file_count = len(objects)
        version.total_size_bytes = sum(o["size"] for o in objects)
        version.status = ModelVersionStatus.AVAILABLE
    elif version.upload_job_name:
        version.status = ModelVersionStatus.FAILED
    await db.flush()


@router.post("", response_model=BaseResponse[ModelVersionResponse])
async def register_model(
    req: ModelVersionCreateRequest,
    db: DbDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("models", "write"))],
) -> BaseResponse[ModelVersionResponse]:
    tenant_id = _require_tenant_id(user)

    tenant = await _get_tenant_or_fail(db, tenant_id)
    namespace = tenant.k8s_namespace_name or make_namespace_name(tenant.name)

    training_job: TrainingJob | None = None
    dataset_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    image_id: uuid.UUID | None = None
    hyperparameters: dict[str, str] | None = None

    if req.training_job_id:
        training_job = await _get_training_job_or_fail(db, req.training_job_id, tenant_id)
        dataset_id = training_job.dataset_id
        dataset_version_id = training_job.dataset_version_id
        image_id = training_job.image_id
        hyperparameters = training_job.hyperparameters

    model = await _get_or_create_registered_model(db, tenant_id, user.id, req.name)

    version_number = await _next_version_number(db, model.id)
    storage_path = f"models/{sanitize_k8s_name(req.name)}/v{version_number}"

    workspace_host_path = make_workspace_host_path(tenant.name)
    short_id = uuid.uuid4().hex[:8]
    upload_job_name = f"kubeai-upload-{short_id}"

    bucket = await minio.ensure_bucket(tenant.name)
    upload_job = build_upload_job(
        namespace=namespace,
        job_name=upload_job_name,
        workspace_host_path=workspace_host_path,
        source_paths=req.file_paths,
        minio_endpoint=f"http://{settings.MINIO_ENDPOINT}",
        minio_access_key=settings.MINIO_ACCESS_KEY,
        minio_secret_key=settings.MINIO_SECRET_KEY,
        minio_bucket=bucket,
        target_path=storage_path,
    )

    try:
        await create_upload_job(namespace, upload_job)
    except Exception as e:
        raise BadRequestException(f"上传任务创建失败: {e}") from e

    version = ModelVersion(
        registered_model_id=model.id,
        version_number=version_number,
        description=req.description,
        storage_path=storage_path,
        status=ModelVersionStatus.UPLOADING,
        upload_job_name=upload_job_name,
        file_count=len(req.file_paths),
        total_size_bytes=0,
        training_job_id=req.training_job_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        image_id=image_id,
        hyperparameters=hyperparameters,
        created_by=user.id,
    )
    db.add(version)

    audit_service = AuditService(db)
    await audit_service.log_action(
        action="register",
        resource_type="model",
        ip_address=_audit_ctx(request, user)["ip_address"],
        user_id=user.id,
        tenant_id=tenant_id,
        resource_id=str(version.id),
        detail={"model_name": req.name, "version_number": version_number, "file_paths": req.file_paths},
        user_agent=_audit_ctx(request, user).get("user_agent"),
        request_id=_audit_ctx(request, user).get("request_id"),
    )

    await db.flush()
    await db.refresh(version)
    return BaseResponse(data=_build_version_response(version), message="模型注册成功")


@router.post("/local-upload", response_model=BaseResponse[ModelVersionResponse])
async def register_model_local(
    db: DbDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("models", "write"))],
    name: str | None = Form(None, min_length=1, max_length=200),
    description: str | None = Form(None),
    model_id: uuid.UUID | None = Form(None),  # noqa: B008
    training_job_id: uuid.UUID | None = Form(None),  # noqa: B008
    files: list[UploadFile] = File(..., min_length=1),  # noqa: B008
) -> BaseResponse[ModelVersionResponse]:
    """本地上传模型文件到 MinIO，同步完成上传后标记为 AVAILABLE。"""  # noqa: RUF002
    if not model_id and not name:
        raise BadRequestException("请提供模型名称或模型 ID")
    tenant_id = _require_tenant_id(user)
    tenant = await _get_tenant_or_fail(db, tenant_id)

    # 关联训练任务（可选）  # noqa: RUF003
    dataset_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    image_id: uuid.UUID | None = None
    hyperparameters: dict[str, str] | None = None
    if training_job_id:
        training_job = await _get_training_job_or_fail(db, training_job_id, tenant_id)
        dataset_id = training_job.dataset_id
        dataset_version_id = training_job.dataset_version_id
        image_id = training_job.image_id
        hyperparameters = training_job.hyperparameters

    # 定位模型: 指定 model_id 则直接定位; 否则按名称查找/创建
    if model_id:
        await _verify_model_tenant(db, model_id, tenant_id)
        result = await db.execute(select(RegisteredModel).where(RegisteredModel.id == model_id))
        model = result.scalar_one()
    else:
        assert name is not None  # validated above
        model = await _get_or_create_registered_model(db, tenant_id, user.id, name)

    version_number = await _next_version_number(db, model.id)
    storage_path = f"models/{sanitize_k8s_name(model.name)}/v{version_number}"

    # 确保 MinIO bucket 存在
    await minio.ensure_bucket(tenant.name)

    # 逐个上传文件到 MinIO
    total_size = 0
    file_count = 0
    for file in files:
        content = await file.read()
        object_name = f"{storage_path}/{file.filename}"
        try:
            await minio.upload_stream(
                tenant_name=tenant.name,
                object_name=object_name,
                data=io.BytesIO(content),
                length=len(content),
                content_type=file.content_type or "application/octet-stream",
            )
        except Exception as e:
            raise BadRequestException(f"文件上传失败: {file.filename} - {e}") from e
        total_size += len(content)
        file_count += 1

    # 创建模型版本记录（直接标记为 AVAILABLE）  # noqa: RUF003
    version = ModelVersion(
        registered_model_id=model.id,
        version_number=version_number,
        description=description,
        storage_path=storage_path,
        status=ModelVersionStatus.AVAILABLE,
        upload_job_name=None,
        file_count=file_count,
        total_size_bytes=total_size,
        training_job_id=training_job_id,
        dataset_id=dataset_id,
        dataset_version_id=dataset_version_id,
        image_id=image_id,
        hyperparameters=hyperparameters,
        created_by=user.id,
    )
    db.add(version)

    # 审计日志
    audit_service = AuditService(db)
    await audit_service.log_action(
        action="register",
        resource_type="model",
        ip_address=_audit_ctx(request, user)["ip_address"],
        user_id=user.id,
        tenant_id=tenant_id,
        resource_id=str(version.id),
        detail={
            "model_name": model.name,
            "version_number": version_number,
            "file_count": file_count,
            "total_size_bytes": total_size,
            "upload_method": "local",
        },
        user_agent=_audit_ctx(request, user).get("user_agent"),
        request_id=_audit_ctx(request, user).get("request_id"),
    )

    await db.flush()
    await db.refresh(version)
    return BaseResponse(data=_build_version_response(version), message="模型本地上传成功")


@router.get("", response_model=PageResponse[RegisteredModelResponse])
async def list_models(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=100),
) -> PageResponse[RegisteredModelResponse]:
    tenant_id = _require_tenant_id(user)
    query = select(RegisteredModel).where(RegisteredModel.tenant_id == tenant_id)
    if search:
        query = query.where(RegisteredModel.name.ilike(f"%{search}%"))

    total_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_q)).scalar_one()

    result = await db.execute(
        query.order_by(RegisteredModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    models = list(result.scalars().all())

    user_name_map = await _resolve_user_names(db, models)
    all_versions = [v for m in models for v in m.versions]
    training_job_names = await _resolve_training_job_names(db, all_versions)
    dataset_names, dataset_version_numbers = await _resolve_dataset_info(db, all_versions)
    image_info = await _resolve_image_info(db, all_versions)
    items = [
        _build_model_response(m, user_name_map, training_job_names, dataset_names, dataset_version_numbers, image_info)
        for m in models
    ]
    page_data = PageData(items=items, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{model_id}", response_model=BaseResponse[RegisteredModelDetailResponse])
async def get_model(
    model_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
) -> BaseResponse[RegisteredModelDetailResponse]:
    tenant_id = _require_tenant_id(user)
    result = await db.execute(
        select(RegisteredModel).where(RegisteredModel.id == model_id, RegisteredModel.tenant_id == tenant_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise NotFoundException("模型不存在")

    tenant = await _get_tenant_or_fail(db, tenant_id)
    versions = sorted(model.versions, key=lambda v: v.version_number)

    # Sync uploading versions
    modified = False
    for v in versions:
        if v.status == ModelVersionStatus.UPLOADING:
            await _sync_version_upload_status(v, db, minio, tenant)
            modified = True
    if modified:
        await db.commit()
        for v in versions:
            await db.refresh(v)

    user_name_map = await _resolve_user_names(db, [model])
    training_job_names = await _resolve_training_job_names(db, versions)
    dataset_names, dataset_version_numbers = await _resolve_dataset_info(db, versions)
    image_info = await _resolve_image_info(db, versions)
    base = _build_model_response(
        model, user_name_map, training_job_names, dataset_names, dataset_version_numbers, image_info
    )
    detail = RegisteredModelDetailResponse(
        **base.model_dump(),
        versions=[
            _build_version_response(
                v,
                training_job_names.get(v.training_job_id) if v.training_job_id else None,
                dataset_names.get(v.dataset_id) if v.dataset_id else None,
                dataset_version_numbers.get(v.dataset_version_id) if v.dataset_version_id else None,
                (image_info.get(v.image_id) or (None, None))[0] if v.image_id else None,
                (image_info.get(v.image_id) or (None, None))[1] if v.image_id else None,
            )
            for v in versions
        ],
    )
    return BaseResponse(data=detail, message="获取成功")


@router.get("/{model_id}/versions/{version_id}", response_model=BaseResponse[ModelVersionResponse])
async def get_model_version(
    model_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
) -> BaseResponse[ModelVersionResponse]:
    tenant_id = _require_tenant_id(user)
    result = await db.execute(
        select(ModelVersion).where(
            ModelVersion.id == version_id,
            ModelVersion.registered_model_id == model_id,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise NotFoundException("模型版本不存在")

    await _verify_model_tenant(db, model_id, tenant_id)

    # Sync upload status
    if version.status == ModelVersionStatus.UPLOADING:
        tenant = await _get_tenant_or_fail(db, tenant_id)
        await _sync_version_upload_status(version, db, minio, tenant)
        await db.commit()
        await db.refresh(version)

    training_job_names = await _resolve_training_job_names(db, [version])
    ds_names, ds_ver_nums = await _resolve_dataset_info(db, [version])
    img_info = await _resolve_image_info(db, [version])
    return BaseResponse(
        data=_build_version_response(
            version,
            training_job_names.get(version.training_job_id) if version.training_job_id else None,
            ds_names.get(version.dataset_id) if version.dataset_id else None,
            ds_ver_nums.get(version.dataset_version_id) if version.dataset_version_id else None,
            (img_info.get(version.image_id) or (None, None))[0] if version.image_id else None,
            (img_info.get(version.image_id) or (None, None))[1] if version.image_id else None,
        ),
        message="获取成功",
    )


@router.get("/{model_id}/versions/{version_id}/files", response_model=BaseResponse[list[ModelVersionFileResponse]])
async def list_version_files(
    model_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
) -> BaseResponse[list[ModelVersionFileResponse]]:
    tenant_id = _require_tenant_id(user)
    version = await _get_version_or_fail(db, version_id, model_id)
    await _verify_model_tenant(db, model_id, tenant_id)

    if version.status != ModelVersionStatus.AVAILABLE:
        raise BadRequestException("模型文件尚未上传完成")

    tenant = await _get_tenant_or_fail(db, tenant_id)
    prefix = version.storage_path
    objects = await minio.list_objects(tenant.name, prefix)

    files: list[ModelVersionFileResponse] = []
    for obj in objects:
        # Strip prefix to get relative file name
        object_name: str = obj["object_name"]
        file_name = object_name[len(prefix) + 1 :] if object_name.startswith(prefix + "/") else object_name
        files.append(
            ModelVersionFileResponse(
                file_name=file_name,
                size_bytes=obj["size"],
                content_type=obj["content_type"],
                last_modified=obj.get("last_modified"),
            )
        )
    return BaseResponse(data=files, message="获取成功")


@router.post("/{model_id}/versions/{version_id}/files/download-url", response_model=BaseResponse[str])
async def get_file_download_url(
    model_id: uuid.UUID,
    version_id: uuid.UUID,
    body: ModelFileDownloadRequest,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
) -> BaseResponse[str]:
    tenant_id = _require_tenant_id(user)
    version = await _get_version_or_fail(db, version_id, model_id)
    await _verify_model_tenant(db, model_id, tenant_id)

    if version.status != ModelVersionStatus.AVAILABLE:
        raise BadRequestException("模型文件尚未上传完成")

    tenant = await _get_tenant_or_fail(db, tenant_id)
    object_name = f"{version.storage_path}/{body.file_name}"
    url = await minio.presigned_get_url(tenant.name, object_name, download_filename=body.file_name)
    return BaseResponse(data=url, message="获取成功")


async def _get_version_or_fail(db: AsyncSession, version_id: uuid.UUID, model_id: uuid.UUID) -> ModelVersion:
    result = await db.execute(
        select(ModelVersion).where(
            ModelVersion.id == version_id,
            ModelVersion.registered_model_id == model_id,
        )
    )
    version = result.scalar_one_or_none()
    if not version:
        raise NotFoundException("模型版本不存在")
    return version


async def _get_tenant_or_fail(db: AsyncSession, tenant_id: uuid.UUID) -> Tenant:
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise NotFoundException("租户不存在")
    return tenant


async def _get_training_job_or_fail(db: AsyncSession, job_id: uuid.UUID, tenant_id: uuid.UUID) -> TrainingJob:
    result = await db.execute(select(TrainingJob).where(TrainingJob.id == job_id, TrainingJob.tenant_id == tenant_id))
    job = result.scalar_one_or_none()
    if not job:
        raise NotFoundException("训练任务不存在")
    return job


async def _get_or_create_registered_model(
    db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID, name: str
) -> RegisteredModel:
    result = await db.execute(
        select(RegisteredModel).where(RegisteredModel.tenant_id == tenant_id, RegisteredModel.name == name)
    )
    model = result.scalar_one_or_none()
    if model:
        return model
    model = RegisteredModel(tenant_id=tenant_id, name=name, created_by=user_id)
    db.add(model)
    await db.flush()
    return model


async def _next_version_number(db: AsyncSession, model_id: uuid.UUID) -> int:
    result = await db.execute(
        select(func.max(ModelVersion.version_number)).where(ModelVersion.registered_model_id == model_id)
    )
    max_ver = result.scalar_one_or_none()
    return (max_ver or 0) + 1


async def _verify_model_tenant(db: AsyncSession, model_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    result = await db.execute(select(RegisteredModel.tenant_id).where(RegisteredModel.id == model_id))
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundException("模型不存在")
    if row != tenant_id:
        from app.core.exceptions import ForbiddenException

        raise ForbiddenException("无权访问其他租户的资源")


async def _delete_version_minio_objects(minio: MinIOClient, tenant_name: str, storage_path: str) -> int:
    """Delete all MinIO objects under a version's storage_path prefix. Returns count of deleted objects."""
    try:
        objects = await minio.list_objects(tenant_name, storage_path)
    except Exception:
        return 0
    if not objects:
        return 0
    object_names = [o["object_name"] for o in objects]
    await minio.delete_objects(tenant_name, object_names)
    return len(object_names)


@router.delete("/{model_id}/versions/{version_id}", response_model=BaseResponse[None])
async def delete_model_version(
    model_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "manage"))],
) -> BaseResponse[None]:
    """删除指定模型版本及其 MinIO 文件。"""
    tenant_id = _require_tenant_id(user)
    await _verify_model_tenant(db, model_id, tenant_id)
    version = await _get_version_or_fail(db, version_id, model_id)

    # 检查是否还有其它版本 — 至少保留一个版本时不能删最后一个版本通过模型级删除
    result = await db.execute(select(func.count(ModelVersion.id)).where(ModelVersion.registered_model_id == model_id))
    version_count = result.scalar_one()
    if version_count <= 1:
        raise BadRequestException("模型至少需要保留一个版本，请直接删除整个模型")  # noqa: RUF001

    # 删除 MinIO 文件
    tenant = await _get_tenant_or_fail(db, tenant_id)
    deleted_count = await _delete_version_minio_objects(minio, tenant.name, version.storage_path)

    # 删除 DB 记录
    await db.delete(version)
    await db.commit()

    return BaseResponse(message=f"版本 v{version.version_number} 已删除（清理了 {deleted_count} 个文件）")  # noqa: RUF001


@router.delete("/{model_id}", response_model=BaseResponse[None])
async def delete_registered_model(
    model_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    request: Request,
    user: Annotated[CurrentUser, Depends(require_permission("models", "manage"))],
) -> BaseResponse[None]:
    """删除整个模型及其所有版本和 MinIO 文件。"""
    tenant_id = _require_tenant_id(user)
    await _verify_model_tenant(db, model_id, tenant_id)

    result = await db.execute(select(RegisteredModel).where(RegisteredModel.id == model_id))
    model = result.scalar_one()

    # 删除所有版本的 MinIO 文件
    tenant = await _get_tenant_or_fail(db, tenant_id)
    total_deleted = 0
    for version in model.versions:
        total_deleted += await _delete_version_minio_objects(minio, tenant.name, version.storage_path)

    # 审计日志
    audit_service = AuditService(db)
    await audit_service.log_action(
        action="delete",
        resource_type="model",
        ip_address=_audit_ctx(request, user)["ip_address"],
        user_id=user.id,
        tenant_id=tenant_id,
        resource_id=str(model_id),
        detail={
            "model_name": model.name,
            "version_count": len(model.versions),
            "files_deleted": total_deleted,
        },
        user_agent=_audit_ctx(request, user).get("user_agent"),
        request_id=_audit_ctx(request, user).get("request_id"),
    )

    # 级联删除(RegisteredModel -> ModelVersion via cascade)
    await db.delete(model)
    await db.commit()

    return BaseResponse(
        message=f"模型 {model.name} 已删除（清理了 {len(model.versions)} 个版本、{total_deleted} 个文件）"  # noqa: RUF001
    )
