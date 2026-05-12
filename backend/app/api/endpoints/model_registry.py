import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.config import settings
from app.core.events import get_minio_client
from app.core.exceptions import BadRequestException, NotFoundException
from app.integrations.base import sanitize_k8s_name
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.k8s.pvc import make_workspace_host_path
from app.integrations.k8s.upload_job import build_upload_job, create_upload_job
from app.integrations.minio import MinIOClient
from app.models.registered_model import ModelVersion, RegisteredModel
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.models.user import User
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.model_registry import (
    ModelVersionCreateRequest,
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
) -> RegisteredModelResponse:
    versions = sorted(model.versions, key=lambda v: v.version_number)
    latest = versions[-1] if versions else None
    return RegisteredModelResponse(
        id=model.id,
        name=model.name,
        description=model.description,
        tenant_id=model.tenant_id,
        created_by=model.created_by,
        created_by_name=(user_name_map or {}).get(model.created_by),
        version_count=len(versions),
        latest_version=_build_version_response(latest) if latest else None,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _build_version_response(v: ModelVersion) -> ModelVersionResponse:
    return ModelVersionResponse(
        id=v.id,
        registered_model_id=v.registered_model_id,
        version_number=v.version_number,
        description=v.description,
        storage_path=v.storage_path,
        file_count=v.file_count,
        total_size_bytes=v.total_size_bytes,
        training_job_id=v.training_job_id,
        dataset_id=v.dataset_id,
        dataset_version_id=v.dataset_version_id,
        image_id=v.image_id,
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

    bucket = minio._bucket_name(tenant.name)
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


@router.get("", response_model=PageResponse[RegisteredModelResponse])
async def list_models(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[RegisteredModelResponse]:
    tenant_id = _require_tenant_id(user)
    query = select(RegisteredModel).where(RegisteredModel.tenant_id == tenant_id)

    total_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(total_q)).scalar_one()

    result = await db.execute(
        query.order_by(RegisteredModel.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    models = list(result.scalars().all())

    user_name_map = await _resolve_user_names(db, models)
    items = [_build_model_response(m, user_name_map) for m in models]
    page_data = PageData(items=items, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{model_id}", response_model=BaseResponse[RegisteredModelDetailResponse])
async def get_model(
    model_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
) -> BaseResponse[RegisteredModelDetailResponse]:
    tenant_id = _require_tenant_id(user)
    result = await db.execute(
        select(RegisteredModel).where(RegisteredModel.id == model_id, RegisteredModel.tenant_id == tenant_id)
    )
    model = result.scalar_one_or_none()
    if not model:
        raise NotFoundException("模型不存在")

    user_name_map = await _resolve_user_names(db, [model])
    base = _build_model_response(model, user_name_map)
    versions = sorted(model.versions, key=lambda v: v.version_number)
    detail = RegisteredModelDetailResponse(
        **base.model_dump(),
        versions=[_build_version_response(v) for v in versions],
    )
    return BaseResponse(data=detail, message="获取成功")


@router.get("/{model_id}/versions/{version_id}", response_model=BaseResponse[ModelVersionResponse])
async def get_model_version(
    model_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
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
    return BaseResponse(data=_build_version_response(version), message="获取成功")


@router.get("/{model_id}/versions/{version_id}/download", response_model=BaseResponse[str])
async def download_model_version(
    model_id: uuid.UUID,
    version_id: uuid.UUID,
    db: DbDep,
    minio: MinioDep,
    user: Annotated[CurrentUser, Depends(require_permission("models", "read"))],
) -> BaseResponse[str]:
    tenant_id = _require_tenant_id(user)
    tenant = await _get_tenant_or_fail(db, tenant_id)
    tenant_name = tenant.name

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

    import asyncio

    url = await asyncio.to_thread(minio.presigned_get_url, tenant_name, version.storage_path)
    return BaseResponse(data=url, message="获取成功")


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
