from typing import Annotated

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db
from app.core.config import settings
from app.core.redis import get_redis
from app.core.security import decode_token
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
from app.services.auth_service import AuthService
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
