import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.models.inference_service import InferenceService
from app.models.registered_model import ModelVersion
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.inference_service import (
    InferenceServiceCreateRequest,
    InferenceServiceCreateResponse,
    InferenceServiceResponse,
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
    return resp


async def _enrich_with_model_version(db: AsyncSession, svc: InferenceServiceResponse) -> InferenceServiceResponse:
    result = await db.execute(select(ModelVersion).where(ModelVersion.id == svc.model_version_id))
    version = result.scalar_one_or_none()
    if version:
        svc.model_version = ModelVersionSummary(
            id=version.id,
            version_number=version.version_number,
            registered_model_id=version.registered_model_id,
            status=version.status,
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
        model_version_id=req.model_version_id,
        gpu_count=req.gpu_count,
        cpu=req.cpu,
        memory=req.memory,
        replicas=req.replicas,
        image=req.image,
        env_vars=req.env_vars,
        description=req.description,
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
