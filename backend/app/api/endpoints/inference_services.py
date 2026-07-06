import uuid
from datetime import datetime
from typing import Annotated, cast

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.auth_helpers import resolve_identity_from_request
from app.core.clients import get_prometheus_client
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.gpu_metrics import MetricsResponse
from app.core.redis import get_redis
from app.integrations.k8s.deployment import list_deployment_events
from app.integrations.k8s.namespace import make_namespace_name
from app.models.enums import InferenceServiceStatus, UserRole
from app.models.inference_service import InferenceService
from app.models.tenant import Tenant
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.inference_service import (
    AutoScalingUpdateRequest,
    InferenceServiceCreateRequest,
    InferenceServiceCreateResponse,
    InferenceServiceEventResponse,
    InferenceServiceResponse,
    InferenceServiceScaleRequest,
    InferenceServiceScaleResponse,
    ModelVersionSummary,
    TokenRegenerateResponse,
)
from app.services.inference_service import InferenceServiceService
from app.tasks.inference_service_tasks import (
    enqueue_inference_service_delete,
    enqueue_inference_service_deploy,
    enqueue_inference_service_scale,
    enqueue_inference_service_start,
    enqueue_inference_service_stop,
)

router = APIRouter(prefix="/inference-services", tags=["inference-services"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
_status_query = Query(None)
_name_query = Query(None)


def _require_tenant_id(user: object) -> uuid.UUID:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise ForbiddenException("需要租户上下文才能操作推理服务")
    return cast("uuid.UUID", tenant_id)


def _extract_bearer_token(request: Request) -> str | None:
    """从 Authorization: Bearer 头提取推理服务级 sk-token (APISIX forward-auth 转发)."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip()
    return None


def _to_response(svc: InferenceService) -> InferenceServiceResponse:
    resp = InferenceServiceResponse.model_validate(svc)
    resp.has_token = svc.auth_token_hash is not None
    resp.error_message = svc.error_message
    if svc.model_version is not None:
        mv = svc.model_version
        resp.model_version = ModelVersionSummary(
            id=mv.id,
            version_number=mv.version_number,
            registered_model_id=mv.registered_model_id,
            model_name=mv.model.name if mv.model else "",
            status=mv.status,
        )
    return resp


@router.post("", response_model=BaseResponse[InferenceServiceCreateResponse])
async def create_inference_service(
    req: InferenceServiceCreateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceCreateResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc, api_token = await service.create_inference_service_record(
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        gpu_count=req.gpu_count,
        cpu=req.cpu,
        memory=req.memory,
        replicas=req.replicas,
        image=req.image,
        image_id=req.image_id,
        container_port=req.container_port,
        command=req.command,
        args=req.args,
        env_vars=req.env_vars,
        description=req.description,
        auto_scaling=req.auto_scaling,
        model_version_id=req.model_version_id,
        subpath_mode=req.subpath_mode,
    )
    await enqueue_inference_service_deploy(svc.id, tenant_id)
    resp = InferenceServiceCreateResponse.model_validate(
        {**{k: v for k, v in svc.__dict__.items() if not k.startswith("_")}, "auth_token": api_token, "has_token": True}
    )
    return BaseResponse(data=resp, message="推理服务创建任务已提交")


@router.get("", response_model=PageResponse[InferenceServiceResponse])
async def list_inference_services(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "read"))],
    status: str | None = _status_query,
    name: str | None = _name_query,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    items, total = await service.list_inference_services(
        tenant_id=tenant_id,
        page=page,
        page_size=page_size,
        status=status,
        name=name,
    )
    resp_list = []
    for svc in items:
        r = _to_response(svc)
        resp_list.append(r)
    page_data = PageData(items=resp_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/auth-check", include_in_schema=False)
async def auth_check_inference_service(
    request: Request,
    service_id: Annotated[uuid.UUID, Query()],
    db: DbDep,
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> Response:
    """APISIX forward-auth 回调: 双通道鉴权.

    1. 浏览器访问 (前后端小项目类服务): Cookie 里的 kubeai_access_token (JWT),
       走 IdentityResolver + 服务归属校验.
    2. 程序化访问 (纯后端 API 对外服务): Authorization: Bearer sk-xxx (服务级
       token), 反查 auth_token_hash + service_id 匹配.

    必须注册在 ``/{service_id}`` 之前, 否则被 catch-all path 参数抢路由.
    2xx 放行, 401/403 由 APISIX 直接拦截 (请求到不了推理 upstream).
    """
    # 通道 1 — 平台登录 Cookie (浏览器).
    identity = await resolve_identity_from_request(request, db, redis)
    if identity:
        if not identity.tenant_id:
            raise ForbiddenException("需要租户上下文")
        service = InferenceServiceService(db)
        try:
            svc = await service.get_inference_service(service_id, identity.tenant_id)
        except Exception:
            raise ForbiddenException("推理服务不存在或无权访问") from None
        if svc.status != InferenceServiceStatus.RUNNING:
            raise ForbiddenException("推理服务未运行")
        if svc.created_by != identity.id and identity.role not in (UserRole.ADMIN, UserRole.MLOPS):
            raise ForbiddenException("无权访问此推理服务")
        return Response(status_code=200, headers={"X-KubeAI-User": identity.username})

    # 通道 2 — 服务级 sk-token (程序化对外调用).
    token = _extract_bearer_token(request)
    if token:
        svc_token = await InferenceServiceService.get_service_by_token(db, token)
        if svc_token and svc_token.id == service_id and svc_token.status == InferenceServiceStatus.RUNNING:
            return Response(status_code=200)
        raise UnauthorizedException("无效的 API Token")

    raise UnauthorizedException("未登录或未提供认证 Token")


@router.get("/{service_id}", response_model=BaseResponse[InferenceServiceResponse])
async def get_inference_service(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "read"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.get_inference_service(service_id, tenant_id)
    resp = _to_response(svc)
    return BaseResponse(data=resp, message="获取成功")


@router.post("/{service_id}/start", response_model=BaseResponse[InferenceServiceResponse])
async def start_inference_service(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.start_inference_service(service_id, tenant_id)
    await enqueue_inference_service_start(svc.id, tenant_id)
    resp = _to_response(svc)
    return BaseResponse(data=resp, message="推理服务启动中")


@router.post("/{service_id}/stop", response_model=BaseResponse[InferenceServiceResponse])
async def stop_inference_service(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.stop_inference_service(service_id, tenant_id)
    await enqueue_inference_service_stop(svc.id, tenant_id)
    resp = _to_response(svc)
    return BaseResponse(data=resp, message="推理服务已停止")


@router.post("/{service_id}/scale", response_model=BaseResponse[InferenceServiceScaleResponse])
async def scale_inference_service(
    service_id: uuid.UUID,
    req: InferenceServiceScaleRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceScaleResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.scale_inference_service(service_id, tenant_id, req.replicas)
    await enqueue_inference_service_scale(svc.id, tenant_id, req.replicas)
    resp = InferenceServiceScaleResponse.model_validate(svc)
    resp.has_token = svc.auth_token_hash is not None
    return BaseResponse(data=resp, message="副本数调整成功")


@router.delete("/{service_id}", response_model=BaseResponse[InferenceServiceResponse])
async def delete_inference_service(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "manage"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    tenant = await db.get(Tenant, tenant_id)
    namespace = (tenant.k8s_namespace_name or make_namespace_name(tenant.name)) if tenant else ""

    # 提取 K8s 资源名 (DB 删除后无法再查询)
    svc = await service.get_inference_service(service_id, tenant_id)

    svc = await service.delete_inference_service(service_id, tenant_id)
    await enqueue_inference_service_delete(
        namespace=namespace,
        scaling_mode=svc.scaling_mode,
        k8s_deployment_name=svc.k8s_deployment_name,
        k8s_service_name=svc.k8s_service_name,
        service_id=svc.id,
    )
    resp = _to_response(svc)
    return BaseResponse(data=resp, message="推理服务已删除")


@router.post("/{service_id}/regenerate-token", response_model=BaseResponse[TokenRegenerateResponse])
async def regenerate_token(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[TokenRegenerateResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    token = await service.regenerate_token(service_id, tenant_id)
    return BaseResponse(
        data=TokenRegenerateResponse(token=token, message="Token 已重新生成"), message="Token 重新生成成功"
    )


@router.patch("/{service_id}/autoscaling", response_model=BaseResponse[InferenceServiceResponse])
async def update_auto_scaling(
    service_id: uuid.UUID,
    req: AutoScalingUpdateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.update_auto_scaling(service_id, tenant_id, req)
    resp = _to_response(svc)
    return BaseResponse(data=resp, message="自动伸缩配置更新成功")


@router.get("/{service_id}/events", response_model=BaseResponse[list[InferenceServiceEventResponse]])
async def get_inference_service_events(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "read"))],
) -> BaseResponse[list[InferenceServiceEventResponse]]:
    tenant_id = _require_tenant_id(user)
    service = InferenceServiceService(db)
    svc = await service.get_inference_service(service_id, tenant_id)

    if svc.status in ("pending", "stopped"):
        return BaseResponse(data=[], message="获取成功")

    tenant = await db.get(Tenant, tenant_id)
    namespace = (tenant.k8s_namespace_name or make_namespace_name(tenant.name)) if tenant else ""

    if svc.k8s_deployment_name:
        raw_events = await list_deployment_events(namespace, svc.k8s_deployment_name)
    else:
        return BaseResponse(data=[], message="获取成功")
    events = [
        InferenceServiceEventResponse(
            type=e["type"],
            reason=e["reason"],
            message=e["message"],
            involved_object_kind=e["involved_object_kind"],
            involved_object_name=e["involved_object_name"],
            count=e["count"],
            first_timestamp=datetime.fromisoformat(e["first_timestamp"]) if e.get("first_timestamp") else None,
            last_timestamp=datetime.fromisoformat(e["last_timestamp"]) if e.get("last_timestamp") else None,
        )
        for e in raw_events
    ]
    return BaseResponse(data=events, message="获取成功")


@router.get("/{service_id}/metrics", response_model=BaseResponse[MetricsResponse])
async def get_inference_service_metrics(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "read"))],
    duration: str = Query("20m", description="历史范围(如 20m/1h)"),
    step: str = Query("15s", description="查询精度"),
) -> BaseResponse[MetricsResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    prom_client = get_prometheus_client()
    data = await service.get_metrics(
        service_id=service_id,
        tenant_id=tenant_id,
        prom_client=prom_client,
        duration=duration,
        step=step,
    )
    return BaseResponse(data=MetricsResponse(**data), message="获取成功")
