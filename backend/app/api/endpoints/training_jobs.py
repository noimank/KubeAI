import json
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, SSECurrentUser, get_db, require_permission
from app.core.events import get_prometheus_client
from app.core.exceptions import ForbiddenException
from app.integrations.base import sanitize_k8s_name
from app.models.user import User
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.training_job import (
    LogResponse,
    PodInfoResponse,
    TrainingJobCreateRequest,
    TrainingJobResponse,
    TrainingMetricsResponse,
)
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


def _to_response(job: object, **kwargs: object) -> TrainingJobResponse:
    data = TrainingJobResponse.model_validate(job).model_dump()
    data.update(kwargs)
    return TrainingJobResponse(**data)


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
        worker_count=req.worker_count,
        metrics_port=req.metrics_port,
    )
    username = getattr(user, "username", "")
    return BaseResponse(
        data=_to_response(job, workspace_path="/workspace", home_path=f"/home/{sanitize_k8s_name(username)}"),
        message="训练任务创建成功",
    )


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
    username = await _resolve_username(db, job.created_by)
    return BaseResponse(
        data=_to_response(job, workspace_path="/workspace", home_path=f"/home/{sanitize_k8s_name(username)}"),
        message="获取成功",
    )


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


@router.post("/{training_job_id}/retry", response_model=BaseResponse[TrainingJobResponse])
async def retry_training_job(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "write"))],
) -> BaseResponse[TrainingJobResponse]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    job = await service.retry_training_job(training_job_id, tenant_id, user.id)
    return BaseResponse(data=_to_response(job), message="重试任务已创建")


@router.get("/{training_job_id}/pods", response_model=BaseResponse[list[PodInfoResponse]])
async def list_training_job_pods(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "read"))],
) -> BaseResponse[list[PodInfoResponse]]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    pods = await service.list_pods(job_id=training_job_id, tenant_id=tenant_id)
    pod_responses = [PodInfoResponse(**p) for p in pods]
    return BaseResponse(data=pod_responses, message="获取成功")


@router.get("/{training_job_id}/logs", response_model=BaseResponse[LogResponse])
async def get_training_job_logs(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "read"))],
    pod_name: str | None = Query(None),
    tail_lines: int = Query(1000, ge=1, le=10000),
) -> BaseResponse[LogResponse]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    lines, has_more, total = await service.get_logs(
        job_id=training_job_id,
        tenant_id=tenant_id,
        pod_name=pod_name,
        tail_lines=tail_lines,
    )
    return BaseResponse(
        data=LogResponse(lines=lines, has_more=has_more, total_lines=total),
        message="获取成功",
    )


@router.get("/{training_job_id}/logs/stream")
async def stream_training_job_logs(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[SSECurrentUser, Depends(require_permission("training_jobs", "read"))],
    pod_name: str | None = Query(None),
    tail_lines: int = Query(100, ge=1, le=10000),
) -> StreamingResponse:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)

    async def event_generator() -> AsyncGenerator[str, None]:
        async for line in service.stream_logs(
            job_id=training_job_id,
            tenant_id=tenant_id,
            pod_name=pod_name,
            tail_lines=tail_lines,
        ):
            yield f"data: {json.dumps({'line': line})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{training_job_id}/metrics", response_model=BaseResponse[TrainingMetricsResponse])
async def get_training_job_metrics(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "read"))],
    duration: str = Query("20m", description="历史范围(如 20m/1h)"),
    step: str = Query("15s", description="查询精度"),
) -> BaseResponse[TrainingMetricsResponse]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    prom_client = get_prometheus_client()
    data = await service.get_metrics(
        job_id=training_job_id,
        tenant_id=tenant_id,
        prom_client=prom_client,
        duration=duration,
        step=step,
    )
    return BaseResponse(data=TrainingMetricsResponse(**data), message="获取成功")


async def _resolve_username(db: AsyncSession, user_id: uuid.UUID) -> str:
    result = await db.execute(select(User.username).where(User.id == user_id))
    row = result.scalar_one_or_none()
    return row or ""
