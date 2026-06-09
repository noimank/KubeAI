import json
import secrets
import uuid
from typing import Annotated, cast
from urllib.parse import urlencode

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.config import settings
from app.core.exceptions import ForbiddenException
from app.core.redis import get_redis
from app.core.security import decode_token
from app.models.dev_environment import DevEnvironment
from app.models.enums import UserRole
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.dev_environment import (
    AccessUrlResponse,
    DevEnvironmentCreateRequest,
    DevEnvironmentResponse,
)
from app.services.dev_environment_service import DevEnvironmentService
from app.tasks.dev_environment_tasks import (
    enqueue_dev_environment_delete,
    enqueue_dev_environment_provision,
    enqueue_dev_environment_start,
    enqueue_dev_environment_stop,
)

router = APIRouter(prefix="/dev-environments", tags=["dev-environments"])

DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]
_status_query = Query(None)
_name_query = Query(None)
OPEN_TICKET_KEY_PREFIX = "dev_environment_open_ticket"
JUPYTERHUB_LOGIN_KEY_PREFIX = "dev_environment_jupyterhub_login"


class JupyterHubLoginRequest(BaseModel):
    token: str = Field(min_length=16, max_length=512)


class JupyterHubLoginResponse(BaseModel):
    name: str


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


def _open_ticket_key(jti: str) -> str:
    return f"{OPEN_TICKET_KEY_PREFIX}:{jti}"


def _jupyterhub_login_key(token: str) -> str:
    return f"{JUPYTERHUB_LOGIN_KEY_PREFIX}:{token}"


@router.post("", response_model=BaseResponse[DevEnvironmentResponse])
async def create_environment(
    req: DevEnvironmentCreateRequest,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "write"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.create_environment_record(
        tenant_id=tenant_id,
        user_id=user.id,
        username=user.username,
        name=req.name,
        environment_image_id=req.environment_image_id,
        gpu_count=req.gpu_count,
        cpu=req.cpu,
        memory=req.memory,
        description=req.description,
        env_vars=req.env_vars,
        datasets=req.datasets,
    )
    await enqueue_dev_environment_provision(env.id, tenant_id, req.algorithm_id)
    return BaseResponse(data=_to_response(env), message="开发环境创建任务已提交")


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


@router.post("/jupyterhub-login", response_model=JupyterHubLoginResponse)
async def jupyterhub_login(
    req: JupyterHubLoginRequest,
    redis: RedisDep,
) -> JupyterHubLoginResponse:
    login_data = await redis.getdel(_jupyterhub_login_key(req.token))
    if not login_data:
        raise ForbiddenException("JupyterHub 登录票据无效或已过期")

    if isinstance(login_data, bytes):
        login_data = login_data.decode("utf-8")
    try:
        payload = json.loads(cast("str", login_data))
    except json.JSONDecodeError:
        raise ForbiddenException("JupyterHub 登录票据无效") from None

    spawner_name = payload.get("spawner_name")
    if not isinstance(spawner_name, str) or not spawner_name:
        raise ForbiddenException("JupyterHub 登录票据无效")
    return JupyterHubLoginResponse(name=spawner_name)


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
    await enqueue_dev_environment_stop(env.id, tenant_id)
    return BaseResponse(data=_to_response(env), message="开发环境停止任务已提交")


@router.post("/{env_id}/start", response_model=BaseResponse[DevEnvironmentResponse])
async def start_environment(
    env_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "write"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.start_environment(env_id, tenant_id)
    await enqueue_dev_environment_start(env.id, tenant_id)
    return BaseResponse(data=_to_response(env), message="开发环境启动任务已提交")


@router.delete("/{env_id}", response_model=BaseResponse[DevEnvironmentResponse])
async def delete_environment(
    env_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "write"))],
) -> BaseResponse[DevEnvironmentResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.get_environment(env_id, tenant_id)
    if env.created_by != user.id and user.role not in (UserRole.ADMIN, UserRole.MLOPS):
        raise ForbiddenException("只能删除自己创建的开发环境")
    await enqueue_dev_environment_delete(env.id, tenant_id)
    return BaseResponse(data=_to_response(env), message="开发环境删除任务已提交")


@router.get("/{env_id}/access-url", response_model=BaseResponse[AccessUrlResponse])
async def get_access_url(
    env_id: uuid.UUID,
    request: Request,
    db: DbDep,
    redis: RedisDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "read"))],
) -> BaseResponse[AccessUrlResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    ticket = await service.create_open_ticket(env_id, tenant_id, user.id)
    payload = decode_token(ticket)
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise ForbiddenException("访问票据生成失败")
    await redis.set(_open_ticket_key(jti), "1", ex=max(30, settings.DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS))
    open_url = str(request.url_for("open_environment", env_id=str(env_id))).split("?")[0]
    url = f"{open_url}?{urlencode({'ticket': ticket})}"
    return BaseResponse(
        data=AccessUrlResponse(access_url=url, message="获取成功"),
        message="获取成功",
    )


@router.get("/{env_id}/open", name="open_environment")
async def open_environment(
    env_id: uuid.UUID,
    ticket: str,
    db: DbDep,
    redis: RedisDep,
) -> RedirectResponse:
    try:
        payload = decode_token(ticket)
    except ValueError:
        raise ForbiddenException("访问票据无效或已过期") from None
    jti = payload.get("jti")
    if not isinstance(jti, str) or not jti:
        raise ForbiddenException("访问票据无效")
    consumed = await redis.getdel(_open_ticket_key(jti))
    if not consumed:
        raise ForbiddenException("访问票据无效或已使用")

    service = DevEnvironmentService(db)
    login_token = secrets.token_urlsafe(32)
    redirect_url, spawner_name = await service.build_hub_login_url_from_ticket(
        ticket,
        env_id,
        login_token=login_token,
    )
    await redis.set(
        _jupyterhub_login_key(login_token),
        json.dumps({"spawner_name": spawner_name}),
        ex=max(30, settings.DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS),
    )
    return RedirectResponse(redirect_url, status_code=302)
