import uuid
from typing import Annotated, cast

import structlog
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.security import decode_token
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

COOKIE_NAME = "kubeai_access_token"
logger = structlog.get_logger(__name__)


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
) -> Response:
    """APISIX forward-auth sub-request — validates the ``kubeai_access_token``
    cookie forwarded by APISIX ``request_headers: [Cookie]`` and returns
    ``X-KubeAI-User`` upstream on success."""

    token = _extract_token_from_request(request)
    if not token:
        raise UnauthorizedException("未登录")

    user = await _validate_token_and_get_user(token, db)
    if not user:
        raise UnauthorizedException("Token 无效或已过期")

    tenant_id = getattr(user, "tenant_id", None)
    if not tenant_id:
        raise ForbiddenException("需要租户上下文")

    service = DevEnvironmentService(db)
    env = await service.get_environment(env_id, tenant_id)
    if env.status != DevEnvironmentStatus.RUNNING:
        raise ForbiddenException("环境未运行")

    if env.created_by != getattr(user, "id", None):
        role = getattr(user, "role", None)
        if role not in (UserRole.ADMIN, UserRole.MLOPS):
            raise ForbiddenException("无权访问此环境")

    username = getattr(user, "username", "")
    logger.info("dev_env_auth_check_success", env_id=str(env_id), username=username)
    return Response(status_code=200, headers={"X-KubeAI-User": username})


def _extract_token_from_request(request: Request) -> str | None:
    """Extract JWT from the forwarded request.

    1. Cookie (forwarded by APISIX ``request_headers: [Cookie]``)
    2. Bearer header (programmatic / API access)
    """
    # 1. Cookie — primary path, forwarding configured in APISIX route
    token = request.cookies.get(COOKIE_NAME)
    if token:
        return token.strip()

    # 2. Raw Cookie header parse — fallback for ASGI / proxy edge cases
    raw_cookie = request.headers.get("Cookie", "")
    if raw_cookie:
        for part in raw_cookie.split(";"):
            part = part.strip()
            if part.startswith(COOKIE_NAME + "="):
                token = part[len(COOKIE_NAME) + 1 :]
                if token:
                    return token.strip()

    # 3. Bearer header — programmatic access
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return None


async def _validate_token_and_get_user(token: str, db: AsyncSession) -> object:
    """Validate JWT and return the User row. Returns None on any failure."""
    try:
        payload = decode_token(token)
    except ValueError:
        return None
    if payload.get("type") != "access":
        return None

    from sqlalchemy import select

    from app.models.user import User as UserModel

    user_id = payload.get("sub")
    if not user_id:
        return None

    result = await db.execute(select(UserModel).where(UserModel.id == user_id))
    user = result.scalar_one_or_none()
    return user if (user and getattr(user, "is_active", False)) else None


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
