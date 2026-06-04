import uuid
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.events import get_prometheus_client
from app.core.exceptions import ForbiddenException
from app.integrations.k8s.deployment import list_deployment_events
from app.integrations.k8s.namespace import make_namespace_name
from app.integrations.kserve.client import list_inference_service_events
from app.models.inference_service import InferenceService
from app.models.registered_model import ModelVersion
from app.models.tenant import Tenant
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.inference_service import (
    AutoScalingUpdateRequest,
    CanaryStartRequest,
    CanaryStatusResponse,
    CanaryTrafficUpdateRequest,
    InferenceServiceCreateRequest,
    InferenceServiceCreateResponse,
    InferenceServiceEventResponse,
    InferenceServiceMetricsResponse,
    InferenceServiceResponse,
    InferenceServiceScaleRequest,
    InferenceServiceScaleResponse,
    ModelVersionSummary,
    TokenRegenerateResponse,
)
from app.services.inference_service import InferenceServiceService

router = APIRouter(prefix="/inference-services", tags=["inference-services"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
_status_query = Query(None)
_name_query = Query(None)


def _require_tenant_id(user: object) -> uuid.UUID:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise ForbiddenException("需要租户上下文才能操作推理服务")
    return cast("uuid.UUID", tenant_id)


def _to_response(svc: InferenceService) -> InferenceServiceResponse:
    resp = InferenceServiceResponse.model_validate(svc)
    resp.has_token = svc.auth_token_hash is not None
    resp.error_message = svc.error_message
    return resp


async def _enrich_with_model_version(db: AsyncSession, svc: InferenceServiceResponse) -> InferenceServiceResponse:
    if svc.model_version_id is None:
        return svc
    result = await db.execute(select(ModelVersion).where(ModelVersion.id == svc.model_version_id))
    version = result.scalar_one_or_none()
    if version:
        svc.model_version = ModelVersionSummary(
            id=version.id,
            version_number=version.version_number,
            registered_model_id=version.registered_model_id,
            status=version.status,
            storage_path=version.storage_path,
        )
    return svc


@router.post("", response_model=BaseResponse[InferenceServiceCreateResponse])
async def create_inference_service(
    req: InferenceServiceCreateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceCreateResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc, api_token = await service.create_inference_service(
        tenant_id=tenant_id,
        user_id=user.id,
        name=req.name,
        service_type=req.service_type,
        model_version_id=req.model_version_id,
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
    )
    resp = InferenceServiceCreateResponse.model_validate(
        {**{k: v for k, v in svc.__dict__.items() if not k.startswith("_")}, "auth_token": api_token, "has_token": True}
    )
    await _enrich_with_model_version(db, resp)
    return BaseResponse(data=resp, message="推理服务创建成功")


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
        r = await _enrich_with_model_version(db, r)
        resp_list.append(r)
    page_data = PageData(items=resp_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


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
    resp = await _enrich_with_model_version(db, resp)
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
    svc = await service.delete_inference_service(service_id, tenant_id)
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

    if svc.service_type == "custom" and svc.k8s_deployment_name:
        raw_events = await list_deployment_events(namespace, svc.k8s_deployment_name)
    elif svc.kserve_name:
        raw_events = await list_inference_service_events(namespace, svc.kserve_name)
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


@router.get("/{service_id}/metrics", response_model=BaseResponse[InferenceServiceMetricsResponse])
async def get_inference_service_metrics(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "read"))],
    duration: str = Query("20m", description="历史范围(如 20m/1h)"),
    step: str = Query("15s", description="查询精度"),
) -> BaseResponse[InferenceServiceMetricsResponse]:
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
    return BaseResponse(data=InferenceServiceMetricsResponse(**data), message="获取成功")


# ── Canary endpoints ────────────────────────────────────────────────────────


@router.post("/{service_id}/canary/start", response_model=BaseResponse[InferenceServiceResponse])
async def start_canary(
    service_id: uuid.UUID,
    req: CanaryStartRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.start_canary(service_id, tenant_id, req)
    resp = _to_response(svc)
    await _enrich_with_model_version(db, resp)
    return BaseResponse(data=resp, message="金丝雀版本部署中")


@router.patch("/{service_id}/canary/traffic", response_model=BaseResponse[InferenceServiceResponse])
async def update_canary_traffic(
    service_id: uuid.UUID,
    req: CanaryTrafficUpdateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.update_canary_traffic(service_id, tenant_id, req)
    resp = _to_response(svc)
    await _enrich_with_model_version(db, resp)
    return BaseResponse(data=resp, message="金丝雀流量已调整")


@router.post("/{service_id}/canary/promote", response_model=BaseResponse[InferenceServiceResponse])
async def promote_canary(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "manage"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.promote_canary(service_id, tenant_id)
    resp = _to_response(svc)
    await _enrich_with_model_version(db, resp)
    return BaseResponse(data=resp, message="金丝雀版本已提升为稳定版本")


@router.post("/{service_id}/canary/rollback", response_model=BaseResponse[InferenceServiceResponse])
async def rollback_canary(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "write"))],
) -> BaseResponse[InferenceServiceResponse]:
    service = InferenceServiceService(db)
    tenant_id = _require_tenant_id(user)
    svc = await service.rollback_canary(service_id, tenant_id)
    resp = _to_response(svc)
    await _enrich_with_model_version(db, resp)
    return BaseResponse(data=resp, message="金丝雀版本已回滚")


@router.get("/{service_id}/canary/status", response_model=BaseResponse[CanaryStatusResponse])
async def get_canary_status(
    service_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("inference_services", "read"))],
) -> BaseResponse[CanaryStatusResponse]:
    tenant_id = _require_tenant_id(user)
    service = InferenceServiceService(db)
    svc = await service.get_inference_service(service_id, tenant_id)

    canary_model_version: ModelVersionSummary | None = None
    if svc.canary_model_version_id:
        result = await db.execute(select(ModelVersion).where(ModelVersion.id == svc.canary_model_version_id))
        version = result.scalar_one_or_none()
        if version:
            canary_model_version = ModelVersionSummary(
                id=version.id,
                version_number=version.version_number,
                registered_model_id=version.registered_model_id,
                status=version.status,
                storage_path=version.storage_path,
            )

    canary_endpoint_url = await service.get_canary_endpoint_url(svc, tenant_id)

    canary_events: list[InferenceServiceEventResponse] = []
    if svc.canary_kserve_name and svc.canary_status != "none":
        tenant = await db.get(Tenant, tenant_id)
        namespace = (tenant.k8s_namespace_name or make_namespace_name(tenant.name)) if tenant else ""
        raw_events = await list_inference_service_events(namespace, svc.canary_kserve_name)
        canary_events = [
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

    data = CanaryStatusResponse(
        canary_status=svc.canary_status,
        canary_model_version=canary_model_version,
        canary_traffic_percent=svc.canary_traffic_percent,
        stable_traffic_percent=100 - svc.canary_traffic_percent if svc.canary_traffic_percent is not None else None,
        canary_endpoint_url=canary_endpoint_url,
        canary_events=canary_events,
    )
    return BaseResponse(data=data, message="获取成功")
