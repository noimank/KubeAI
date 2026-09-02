import uuid
from typing import Annotated, cast

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.auth_helpers import resolve_identity_from_request
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.redis import get_redis
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus, UserRole
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
_status_query = Query(None)
_name_query = Query(None)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Auth-check cache — avoid hammering the DB on every static-file sub-request.
# Jupyter alone fires ~30 forward-auth checks per page load, all for the same
# (env, user) pair.  Caching the "allowed" verdict for 30 s eliminates the DB
# query on every subsequent sub-request while remaining short enough that
# stop/delete is promptly effective.  (When the env is stopped its APISIX route
# is deleted anyway, so no new auth-checks arrive.)
# ---------------------------------------------------------------------------

_DEV_ENV_AUTH_CACHE_PREFIX = "dev_env_auth"
_DEV_ENV_AUTH_CACHE_TTL = 30


def _env_auth_cache_key(env_id: uuid.UUID, user_id: uuid.UUID) -> str:
    return f"{_DEV_ENV_AUTH_CACHE_PREFIX}:{env_id.hex}:{user_id.hex}"


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


# ---------------------------------------------------------------------------
# CRUD — collection endpoints
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# APISIX forward-auth — MUST be registered BEFORE /{env_id} to avoid route
# conflict with HTTPBearer dependency on the catch-all path parameter.
# ---------------------------------------------------------------------------


@router.get("/auth-check", include_in_schema=False)
async def auth_check_dev_environment(
    request: Request,
    env_id: Annotated[uuid.UUID, Query()],
    db: Annotated[AsyncSession, Depends(get_db)],
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
) -> Response:
    """APISIX forward-auth sub-request — validates the ``kubeai_access_token``
    cookie forwarded by APISIX ``request_headers: [Cookie]`` and returns
    ``X-KubeAI-User`` upstream on success.

    身份解析 (JWT / 黑名单 / 用户与租户状态) 统一由 IdentityResolver 完成.
    """
    identity = await resolve_identity_from_request(request, db, redis)
    if not identity:
        raise UnauthorizedException("未登录或 Token 无效")
    if not identity.tenant_id:
        raise ForbiddenException("需要租户上下文")

    # Short-circuit: if this (env, user) pair was recently authorized, skip the
    # DB query.  Cached for 30 s — enough to cover a Jupyter page-load burst
    # while still reflecting stop/delete within a reasonable window.
    if redis is not None:
        cache_key = _env_auth_cache_key(env_id, identity.id)
        if await redis.get(cache_key) == b"1":
            return Response(status_code=200, headers={"X-KubeAI-User": identity.username})

    service = DevEnvironmentService(db)
    env = await service.get_environment(env_id, identity.tenant_id)
    if env.status != DevEnvironmentStatus.RUNNING:
        raise ForbiddenException("环境未运行")

    if env.created_by != identity.id and identity.role not in (UserRole.ADMIN, UserRole.MLOPS):
        raise ForbiddenException("无权访问此环境")

    if redis is not None:
        await redis.setex(_env_auth_cache_key(env_id, identity.id), _DEV_ENV_AUTH_CACHE_TTL, "1")

    # debug — forward-auth fires on every sub-request; logging every success at
    # info level drowns the log in noise.
    logger.debug("dev_env_auth_check_success", env_id=str(env_id), username=identity.username)
    return Response(status_code=200, headers={"X-KubeAI-User": identity.username})


# ---------------------------------------------------------------------------
# CRUD — individual resource (/{env_id} MUST come AFTER explicit paths)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Access URL
# ---------------------------------------------------------------------------


@router.get("/{env_id}/access-url", response_model=BaseResponse[AccessUrlResponse])
async def get_access_url(
    env_id: uuid.UUID,
    db: DbDep,
    user: Annotated[CurrentUser, Depends(require_permission("dev_environments", "read"))],
) -> BaseResponse[AccessUrlResponse]:
    tenant_id = _require_tenant_id(user)
    service = DevEnvironmentService(db)
    env = await service.get_environment(env_id, tenant_id)
    if env.status != DevEnvironmentStatus.RUNNING:
        raise ForbiddenException("环境未运行, 无法获取访问地址")
    url = service.build_access_url(env)
    return BaseResponse(
        data=AccessUrlResponse(access_url=url, message="获取成功"),
        message="获取成功",
    )
