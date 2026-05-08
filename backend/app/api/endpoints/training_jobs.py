import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.training_job import TrainingJobCreateRequest, TrainingJobResponse
from app.services.training_job_service import TrainingJobService

router = APIRouter(prefix="/training-jobs", tags=["training-jobs"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
_status_query = Query(None)
_name_query = Query(None)


def _require_tenant_id(user: object) -> uuid.UUID:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise ForbiddenException("需要租户上下文才能操作训练任务")
    return cast("uuid.UUID", tenant_id)


def _to_response(job: object) -> TrainingJobResponse:
    return TrainingJobResponse.model_validate(job)


@router.post("", response_model=BaseResponse[TrainingJobResponse])
async def create_training_job(
    req: TrainingJobCreateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "write"))],
) -> BaseResponse[TrainingJobResponse]:
    service = TrainingJobService(db)
    hyperparams = None
    if req.hyperparameters:
        hyperparams = [{"key": h.key, "value": h.value} for h in req.hyperparameters]

    tenant_id = _require_tenant_id(user)
    job = await service.create_training_job(
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        description=req.description,
        dataset_id=req.dataset_id,
        dataset_version_id=req.dataset_version_id,
        image_id=req.image_id,
        command=req.command,
        hyperparameters=hyperparams,
        gpu_count=req.gpu_count,
        gpu_mode=req.gpu_mode,
        cpu=req.cpu,
        memory=req.memory,
        priority=req.priority,
    )
    return BaseResponse(data=_to_response(job), message="训练任务创建成功")


@router.get("", response_model=PageResponse[TrainingJobResponse])
async def list_training_jobs(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "read"))],
    status: str | None = _status_query,
    name: str | None = _name_query,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[TrainingJobResponse]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    items, total = await service.list_training_jobs(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        name=name,
    )
    job_list = [_to_response(job) for job in items]
    page_data = PageData(items=job_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{training_job_id}", response_model=BaseResponse[TrainingJobResponse])
async def get_training_job(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "read"))],
) -> BaseResponse[TrainingJobResponse]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    job = await service.get_training_job(training_job_id, tenant_id)
    return BaseResponse(data=_to_response(job), message="获取成功")


@router.post("/{training_job_id}/stop", response_model=BaseResponse[TrainingJobResponse])
async def stop_training_job(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "write"))],
) -> BaseResponse[TrainingJobResponse]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    job = await service.stop_training_job(training_job_id, tenant_id)
    return BaseResponse(data=_to_response(job), message="任务已停止")
