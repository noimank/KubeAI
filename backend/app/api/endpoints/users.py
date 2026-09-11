import uuid
from datetime import datetime
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db, require_permission
from app.core.exceptions import ForbiddenException
from app.core.identity import invalidate_user_identity
from app.core.redis import get_redis
from app.models.enums import UserRole
from app.schemas.base import BaseResponse, PageData, PageResponse
from app.schemas.user import (
    UserDetailResponse,
    UserResponse,
    UserStatusToggleRequest,
    UserUpdateRequest,
)
from app.services.user_service import UserService


def _audit_ctx(request: Request, user: Any) -> dict[str, Any]:
    return {
        "user_id": user.id,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


router = APIRouter(prefix="/users", tags=["users"])

DbDep = Annotated[AsyncSession, Depends(get_db)]

_OptStr = Annotated[str | None, Query()]
_OptRole = Annotated[UserRole | None, Query()]
_OptBool = Annotated[bool | None, Query()]
_Page = Annotated[int, Query(ge=1)]
_PageSize = Annotated[int, Query(ge=1, le=100)]


@router.get("", response_model=PageResponse[UserResponse])
async def list_users(
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("users", "read"))],
    page: _Page = 1,
    page_size: _PageSize = 20,
    username: _OptStr = None,
    email: _OptStr = None,
    role: _OptRole = None,
    is_active: _OptBool = None,
    start_time: _OptStr = None,
    end_time: _OptStr = None,
) -> PageResponse[UserResponse]:
    service = UserService(db)
    items, total = await service.list_users(
        page=page,
        page_size=page_size,
        username=username,
        email=email,
        role=role,
        is_active=is_active,
        start_time=datetime.fromisoformat(start_time) if start_time else None,
        end_time=datetime.fromisoformat(end_time) if end_time else None,
    )
    user_list = [UserResponse(**item) for item in items]
    page_data = PageData(items=user_list, total=total, page=page, page_size=page_size)
    return PageResponse(data=page_data, message="获取成功")


@router.get("/{user_id}", response_model=BaseResponse[UserDetailResponse])
async def get_user(
    user_id: uuid.UUID,
    db: DbDep,
    _user: Annotated[CurrentUser, Depends(require_permission("users", "read"))],
) -> BaseResponse[UserDetailResponse]:
    service = UserService(db)
    detail = await service.get_user(user_id)
    return BaseResponse(data=UserDetailResponse(**detail), message="获取成功")


@router.put("/{user_id}", response_model=BaseResponse[UserDetailResponse])
async def update_user(
    user_id: uuid.UUID,
    req: UserUpdateRequest,
    db: DbDep,
    request: Request,
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
    user: Annotated[CurrentUser, Depends(require_permission("users", "manage"))],
) -> BaseResponse[UserDetailResponse]:
    data = req.model_dump(exclude_unset=True)
    if user_id == user.id:
        raise ForbiddenException("不能修改自身账户的角色或租户")
    service = UserService(db, redis)
    detail = await service.update_user(user_id, data, audit_context=_audit_ctx(request, user))
    return BaseResponse(data=UserDetailResponse(**detail), message="用户更新成功")


@router.patch("/{user_id}/status", response_model=BaseResponse[UserDetailResponse])
async def toggle_user_status(
    user_id: uuid.UUID,
    req: UserStatusToggleRequest,
    db: DbDep,
    request: Request,
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
    user: Annotated[CurrentUser, Depends(require_permission("users", "manage"))],
) -> BaseResponse[UserDetailResponse]:
    service = UserService(db)
    if user_id == user.id:
        raise ForbiddenException("不能禁用自身账户")
    detail = await service.toggle_user_status(user_id, req.is_active, audit_context=_audit_ctx(request, user))
    # 禁用用户: 使其所有已签发 token 的身份缓存立即失效 (修复历史缺陷 —
    # 原先禁用后 token 在 180min 有效期内仍可用)
    if not req.is_active:
        await invalidate_user_identity(redis, user_id)
    label = "启用" if req.is_active else "禁用"
    return BaseResponse(data=UserDetailResponse(**detail), message=f"用户{label}成功")


@router.delete("/{user_id}", response_model=BaseResponse[None])
async def delete_user(
    user_id: uuid.UUID,
    db: DbDep,
    request: Request,
    redis: Annotated[aioredis.Redis, Depends(get_redis)],
    user: Annotated[CurrentUser, Depends(require_permission("users", "manage"))],
) -> BaseResponse[None]:
    service = UserService(db)
    if user_id == user.id:
        raise ForbiddenException("不能删除自身账户")
    await service.delete_user(user_id, audit_context=_audit_ctx(request, user))
    await invalidate_user_identity(redis, user_id)
    return BaseResponse(message="用户删除成功")
