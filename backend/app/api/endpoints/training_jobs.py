import asyncio
import uuid
from contextlib import suppress
from typing import Annotated, cast

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, authenticate_ws_token, get_db, require_permission
from app.core.auth_helpers import resolve_identity_from_request
from app.core.clients import get_prometheus_client
from app.core.exceptions import AppException, ForbiddenException, UnauthorizedException
from app.core.gpu_metrics import MetricsResponse
from app.core.redis import _redis_pool, get_redis
from app.integrations.k8s.kubeai_volumes import HOME_MOUNT_PATH, WORKSPACE_MOUNT_PATH
from app.models.enums import TrainingJobStatus, UserRole
from app.models.experiment import Experiment
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.training_job import (
    LogResponse,
    PodInfoResponse,
    TrainingJobCreateRequest,
    TrainingJobFromEnvironmentRequest,
    TrainingJobResponse,
)
from app.services.training_job_service import TrainingJobService
from app.tasks.training_job_tasks import (
    enqueue_delete_training_job,
    enqueue_stop_training_job,
    enqueue_submit_training_job,
)

router = APIRouter(prefix="/training-jobs", tags=["training-jobs"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
_status_query = Query(None)
_name_query = Query(None)
logger = structlog.get_logger(__name__)


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
    job = await service.create_training_job_record(
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
        source_experiment_id=req.source_experiment_id,
        mlflow_enabled=req.mlflow_enabled,
        tensorboard_enabled=req.tensorboard_enabled,
    )
    await enqueue_submit_training_job(job.id, tenant_id)
    return BaseResponse(
        data=_to_response(job, workspace_path=WORKSPACE_MOUNT_PATH, home_path=HOME_MOUNT_PATH),
        message="训练任务创建成功",
    )


@router.post("/from-environment", response_model=BaseResponse[TrainingJobResponse])
async def create_from_environment(
    req: TrainingJobFromEnvironmentRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "write"))],
) -> BaseResponse[TrainingJobResponse]:
    tenant_id = _require_tenant_id(user)
    service = TrainingJobService(db)
    hyperparams = None
    if req.hyperparameters:
        hyperparams = [{"key": h.key, "value": h.value} for h in req.hyperparameters]
    job = await service.create_from_environment(
        tenant_id=tenant_id,
        user_id=user.id,
        environment_id=req.environment_id,
        name=req.name,
        command=req.command,
        description=req.description,
        image_id=req.image_id,
        dataset_id=req.dataset_id,
        dataset_version_id=req.dataset_version_id,
        gpu_count=req.gpu_count,
        gpu_mode=req.gpu_mode,
        cpu=req.cpu,
        memory=req.memory,
        priority=req.priority,
        worker_count=req.worker_count,
        hyperparameters=hyperparams,
        mlflow_enabled=req.mlflow_enabled,
        tensorboard_enabled=req.tensorboard_enabled,
    )
    await enqueue_submit_training_job(job.id, tenant_id)
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


# ---------------------------------------------------------------------------
# APISIX forward-auth — MUST be registered BEFORE /{training_job_id} to avoid
# path conflict. Mirrors dev_environments.py:117-151.
# ---------------------------------------------------------------------------


@router.get("/auth-check", include_in_schema=False)
async def auth_check_training_job(
    request: Request,
    job_id: Annotated[uuid.UUID, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> Response:
    """APISIX forward-auth for TensorBoard 可视化访问.

    身份解析 (JWT / 黑名单 / 用户与租户状态) 统一由 IdentityResolver 完成, 此处仅做
    资源级鉴权:
      1. job 存在且租户匹配
      2. 作业非终态 (sidecar 容器已销毁, 无意义放行)
      3. 创建者本人 OR admin/mlops
    """
    identity = await resolve_identity_from_request(request, db, redis)
    if not identity:
        raise UnauthorizedException("未登录或 Token 无效")
    if not identity.tenant_id:
        raise ForbiddenException("需要租户上下文")

    service = TrainingJobService(db)
    try:
        # DB-only fetch: forward-auth fires on every TensorBoard sub-request, so a
        # full get_training_job (K8s sync + commit) here would hammer K8s and the DB.
        job = await service.get_training_job_record(job_id, identity.tenant_id)
    except Exception:
        raise ForbiddenException("训练任务不存在或无权访问") from None

    # 终态任务: sidecar 已随 Pod 销毁, 不再放行 (避免上游 502 误导).
    if job.status in {
        TrainingJobStatus.SUCCEEDED,
        TrainingJobStatus.FAILED,
        TrainingJobStatus.STOPPED,
    }:
        raise ForbiddenException("任务已结束, TensorBoard 服务已销毁")

    if job.created_by != identity.id and identity.role not in (UserRole.ADMIN, UserRole.MLOPS):
        raise ForbiddenException("无权访问此任务的 TensorBoard")

    logger.info("training_job_tensorboard_auth_check_success", job_id=str(job_id), username=identity.username)
    return Response(status_code=200, headers={"X-KubeAI-User": identity.username})


@router.get("/{training_job_id}", response_model=BaseResponse[TrainingJobResponse])
async def get_training_job(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "read"))],
) -> BaseResponse[TrainingJobResponse]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    job = await service.get_training_job(training_job_id, tenant_id)

    # 查询关联的 experiment ID (用于前端跳转实验追踪)
    exp_result = await db.execute(select(Experiment.id).where(Experiment.training_job_id == training_job_id))
    experiment_id = exp_result.scalar_one_or_none()

    return BaseResponse(
        data=_to_response(
            job,
            workspace_path=WORKSPACE_MOUNT_PATH,
            home_path=HOME_MOUNT_PATH,
            experiment_id=experiment_id,
        ),
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
    job = await service.stop_training_job_record(training_job_id, tenant_id)
    await enqueue_stop_training_job(job.id, tenant_id)
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
    await enqueue_submit_training_job(job.id, tenant_id)
    return BaseResponse(data=_to_response(job), message="重试任务已创建")


@router.delete("/{training_job_id}", response_model=BaseResponse[None])
async def delete_training_job(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "write"))],
) -> BaseResponse[None]:
    service = TrainingJobService(db)
    tenant_id = _require_tenant_id(user)
    vcjob_name, namespace, tensorboard_enabled, mlflow_experiment_id = await service.delete_training_job_record(
        training_job_id, tenant_id
    )
    await enqueue_delete_training_job(training_job_id, vcjob_name, namespace, tensorboard_enabled, mlflow_experiment_id)
    return BaseResponse(message="训练任务已删除")


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


@router.websocket("/{training_job_id}/logs/ws")
async def stream_training_job_logs_ws(
    websocket: WebSocket,
    training_job_id: uuid.UUID,
    db: DbDep,
    token: str = Query(...),
    pod_name: str | None = Query(None),
    tail_lines: int = Query(100, ge=1, le=10000),
) -> None:
    # WebSocket 是升级连接, nginx 直接透传, 不受 proxy_buffering 影响
    # (SSE 在双层 nginx 下被 Tengine 缓冲, 运行中日志攒在缓冲区, 任务结束才 flush)。
    # 浏览器 WebSocket 无法设置 Authorization 头, 走 ?token= 鉴权。
    user = await authenticate_ws_token(token, db, _redis_pool)
    if user is None or user.tenant_id is None:
        await websocket.close(code=4001, reason="认证失败")
        return
    tenant_id = user.tenant_id
    await websocket.accept()
    service = TrainingJobService(db)

    async def pump() -> None:
        async for line in service.stream_logs(
            job_id=training_job_id,
            tenant_id=tenant_id,
            pod_name=pod_name,
            tail_lines=tail_lines,
        ):
            await websocket.send_json({"line": line})

    # receive_text 兼任「ping 心跳」与「断开检测」; 客户端断开 → cancel pump,
    # stream_pod_logs 的 finally 随生成器关闭释放 K8s follow 连接。
    pump_task = asyncio.create_task(pump())
    try:
        while True:
            recv = asyncio.create_task(websocket.receive_text())
            done, _ = await asyncio.wait({pump_task, recv}, return_when=asyncio.FIRST_COMPLETED)
            if pump_task in done:
                recv.cancel()
                await pump_task  # EOF 正常返回; 任务不存在/未提交/无 Pod 重新抛出 AppException
                break
            if recv.result() == "ping":  # 否则为客户端消息或 WebSocketDisconnect(上抛)
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except AppException as exc:
        with suppress(Exception):
            await websocket.send_json({"error": exc.message})
    finally:
        pump_task.cancel()
        with suppress(BaseException):
            await pump_task
        with suppress(Exception):
            await websocket.close()


@router.get("/{training_job_id}/metrics", response_model=BaseResponse[MetricsResponse])
async def get_training_job_metrics(
    training_job_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("training_jobs", "read"))],
    duration: str = Query("20m", description="历史范围(如 20m/1h)"),
    step: str = Query("15s", description="查询精度"),
) -> BaseResponse[MetricsResponse]:
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
    return BaseResponse(data=MetricsResponse(**data), message="获取成功")
