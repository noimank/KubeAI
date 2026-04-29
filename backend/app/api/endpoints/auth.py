from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, OptionalCurrentUser, get_db
from app.core.config import settings
from app.core.redis import get_redis
from app.core.security import decode_token, hash_password
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.base import BaseResponse
from app.schemas.oauth import OAuthCallbackRequest, OAuthProviderResponse
from app.schemas.tenant import AcceptInvitationRequest, InvitationInfoResponse
from app.services.auth_service import AuthService
from app.services.invitation_service import InvitationService
from app.services.oauth_service import OAuthService

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer()

DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]


@router.post("/register", response_model=BaseResponse[TokenResponse])
async def register(
    req: RegisterRequest,
    db: DbDep,
    redis: RedisDep,
) -> BaseResponse[TokenResponse]:
    service = AuthService(db, redis)
    token = await service.register(req)
    return BaseResponse(data=token, message="注册成功")


@router.post("/login", response_model=BaseResponse[TokenResponse])
async def login(
    req: LoginRequest,
    db: DbDep,
    redis: RedisDep,
) -> BaseResponse[TokenResponse]:
    service = AuthService(db, redis)
    token = await service.login(req)
    return BaseResponse(data=token, message="登录成功")


@router.post("/refresh", response_model=BaseResponse[TokenResponse])
async def refresh(
    req: RefreshRequest,
    db: DbDep,
    redis: RedisDep,
) -> BaseResponse[TokenResponse]:
    service = AuthService(db, redis)
    token = await service.refresh_tokens(req.refresh_token)
    return BaseResponse(data=token, message="刷新成功")


@router.post("/logout", response_model=BaseResponse[None])
async def logout(
    user: CurrentUser,
    request: Request,
    req: LogoutRequest,
    db: DbDep,
    redis: RedisDep,
) -> BaseResponse[None]:
    credentials: HTTPAuthorizationCredentials = await _bearer(request)  # type: ignore[assignment]
    access_payload = decode_token(credentials.credentials)
    access_jti = access_payload["jti"]
    access_exp = access_payload.get("exp")

    refresh_jti = None
    refresh_exp = None
    if req.refresh_token:
        try:
            refresh_payload = decode_token(req.refresh_token)
            refresh_jti = refresh_payload.get("jti")
            refresh_exp = refresh_payload.get("exp")
        except ValueError:
            pass

    service = AuthService(db, redis)
    await service.logout(str(user.id), access_jti, refresh_jti, access_exp, refresh_exp)
    return BaseResponse(message="已退出登录")


@router.get("/me", response_model=BaseResponse[UserResponse])
async def me(user: CurrentUser) -> BaseResponse[UserResponse]:
    user_response = UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        role=user.role,
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
    )
    return BaseResponse(data=user_response, message="获取成功")


@router.get("/oauth/providers", response_model=BaseResponse[list[OAuthProviderResponse]])
async def oauth_providers() -> BaseResponse[list[OAuthProviderResponse]]:
    providers = []
    if settings.OIDC_ENABLED:
        providers.append(OAuthProviderResponse(name="oidc", display_name=settings.OIDC_DISPLAY_NAME))
    return BaseResponse(data=providers, message="获取成功")


@router.get("/oauth/{provider}/authorize")
async def oauth_authorize(
    provider: str,
    redis: RedisDep,
    db: DbDep,
) -> RedirectResponse:
    if not settings.OIDC_ENABLED or provider != "oidc":
        from app.core.exceptions import NotFoundException

        raise NotFoundException("未知的 OAuth 提供者")

    redirect_uri = f"{settings.FRONTEND_URL}/auth/callback"
    service = OAuthService(db, redis)
    url, _ = await service.get_authorization_url(redirect_uri)
    return RedirectResponse(url=url)


@router.post("/oauth/{provider}/callback", response_model=BaseResponse[TokenResponse])
async def oauth_callback(
    provider: str,
    req: OAuthCallbackRequest,
    db: DbDep,
    redis: RedisDep,
) -> BaseResponse[TokenResponse]:
    if not settings.OIDC_ENABLED or provider != "oidc":
        from app.core.exceptions import NotFoundException

        raise NotFoundException("未知的 OAuth 提供者")

    redirect_uri = f"{settings.FRONTEND_URL}/auth/callback"
    service = OAuthService(db, redis)
    token = await service.handle_callback(req.code, req.state, redirect_uri)
    return BaseResponse(data=token, message="登录成功")


# --- Invitation Endpoints ---


@router.get("/invitation-info", response_model=BaseResponse[InvitationInfoResponse])
async def invitation_info(
    token: str,
    db: DbDep,
) -> BaseResponse[InvitationInfoResponse]:
    service = InvitationService(db)
    info = await service.get_invitation_info(token)
    data = InvitationInfoResponse(**info)
    return BaseResponse(data=data, message="获取成功")


@router.post("/accept-invitation", response_model=BaseResponse[TokenResponse])
async def accept_invitation(
    req: AcceptInvitationRequest,
    db: DbDep,
    redis: RedisDep,
    user: OptionalCurrentUser = None,
) -> BaseResponse[TokenResponse]:
    inv_service = InvitationService(db)
    auth_service = AuthService(db, redis)

    if req.username and req.password:
        # 场景 A: 新用户注册 + 接受邀请
        from sqlalchemy import select

        from app.core.exceptions import ConflictException
        from app.models.user import User as UserModel

        inv_info = await inv_service.get_invitation_info(req.token)

        existing_email = await db.execute(select(UserModel).where(UserModel.email == inv_info["email"]))
        if existing_email.scalar_one_or_none() is not None:
            raise ConflictException("该邮箱已注册, 请先登录后接受邀请")

        existing_name = await db.execute(select(UserModel).where(UserModel.username == req.username))
        if existing_name.scalar_one_or_none() is not None:
            raise ConflictException("用户名已存在")

        new_user = UserModel(
            username=req.username,
            email=inv_info["email"],
            hashed_password=hash_password(req.password),
        )
        db.add(new_user)
        await db.flush()
        await db.refresh(new_user)

        await inv_service.accept_invitation(req.token, new_user.id)
        await db.refresh(new_user)

        tokens = auth_service._generate_tokens(
            str(new_user.id),
            str(new_user.tenant_id) if new_user.tenant_id else None,
        )
        return BaseResponse(data=tokens, message="注册并加入租户成功")
    elif user:
        # 场景 B: 已登录用户接受邀请
        from app.core.exceptions import BadRequestException, ConflictException

        if user.tenant_id and not req.force:
            raise ConflictException("您当前已属于一个租户, 接受邀请将转移到新租户, 请确认操作")

        updated_user = await inv_service.accept_invitation(req.token, user.id)
        if not updated_user:
            raise BadRequestException("接受邀请失败")
        await db.refresh(updated_user)

        tokens = auth_service._generate_tokens(
            str(updated_user.id),
            str(updated_user.tenant_id) if updated_user.tenant_id else None,
        )
        return BaseResponse(data=tokens, message="已加入租户")
    else:
        from app.core.exceptions import BadRequestException

        raise BadRequestException("请提供注册信息或先登录")
