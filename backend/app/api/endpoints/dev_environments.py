import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.models.dev_environment import DevEnvironment
from app.models.enums import UserRole
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.dev_environment import (
    DevEnvironmentCreateRequest,
    DevEnvironmentResponse,
    NotebookUrlResponse,
)
from app.services.dev_environment_service import DevEnvironmentService

router = APIRouter(prefix="/dev-environments", tags=["dev-environments"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
_status_query = Query(None)
_name_query = Query(None)


def _require_tenant_id(user: object) -> uuid.UUID:
    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise ForbiddenException("需要租户上下文才能操作开发环境")
    return cast("uuid.UUID", tenant_id)


def _to_response(env: DevEnvironment) -> DevEnvironmentResponse:
    return DevEnvironmentResponse.model_validate(env)


def _should_filter_by_user(user: object) -> uuid.UUID | None:
    role = getattr(user, "role", None)
    if role in (UserRole.ADMIN, UserRole.MLOPS):
        return None
    return getattr(user, "id", None)


@router.post("", response_model=BaseResponse[DevEnvironmentResponse])
async def create_environment(
    req: DevEnvironmentCreateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "write"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.create_environment(
        tenant_id=tenant_id,
        user_id=user.id,
        username=user.username,
        name=req.name,
        image=req.image,
        gpu_count=req.gpu_count,
        cpu=req.cpu,
        memory=req.memory,
        description=req.description,
        env_vars=req.env_vars,
    )
    return BaseResponse(data=_to_response(env), message="开发环境创建成功")


@router.get("", response_model=PageResponse[DevEnvironmentResponse])
async def list_environments(
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "read"))],
    status: str | None = _status_query,
    name: str | None = _name_query,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> PageResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    user_id_filter = _should_filter_by_user(user)
    service = DevEnvironmentService(db)
    items, total = await service.list_environments(
        tenant_id=tenant_id,
        user_id=user_id_filter,
        page=page,
        page_size=page_size,
        status=status,
        name=name,
    )
    resp_list = [_to_response(env) for env in items]
    page_data = PageData(items=resp_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{env_id}", response_model=BaseResponse[DevEnvironmentResponse])
async def get_environment(
    env_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "read"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.get_environment(env_id, tenant_id)
    return BaseResponse(data=_to_response(env), message="获取成功")


@router.post("/{env_id}/stop", response_model=BaseResponse[DevEnvironmentResponse])
async def stop_environment(
    env_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "write"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.stop_environment(env_id, tenant_id)
    return BaseResponse(data=_to_response(env), message="开发环境已停止")


@router.post("/{env_id}/start", response_model=BaseResponse[DevEnvironmentResponse])
async def start_environment(
    env_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "write"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.start_environment(env_id, tenant_id)
    return BaseResponse(data=_to_response(env), message="开发环境启动中")


@router.delete("/{env_id}", response_model=BaseResponse[DevEnvironmentResponse])
async def delete_environment(
    env_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "manage"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.delete_environment(env_id, tenant_id)
    return BaseResponse(data=_to_response(env), message="开发环境已删除")


@router.get("/{env_id}/notebook-url", response_model=BaseResponse[NotebookUrlResponse])
async def get_notebook_url(
    env_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "read"))],
) -> BaseResponse[NotebookUrlResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    url = await service.get_notebook_url(env_id, tenant_id)
    return BaseResponse(
        data=NotebookUrlResponse(notebook_url=url, message="获取成功"),
        message="获取成功",
    )
