import base64
from typing import Annotated, Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, CurrentUserEntity, OptionalCurrentUser, get_db
from app.core.auth_helpers import resolve_identity_from_request
from app.core.casbin import CasbinEnforcer
from app.core.config import settings
from app.core.exceptions import BadRequestException, ConflictException, ForbiddenException, UnauthorizedException
from app.core.redis import get_redis
from app.core.security import decode_token, hash_password, verify_password
from app.models.enums import AuditAction, ResourceType
from app.models.user import User as UserModel
from app.schemas.auth import (
    AuthConfigResponse,
    LoginRequest,
    LogoutRequest,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.base import BaseResponse
from app.schemas.oauth import OAuthCallbackRequest, OAuthProviderResponse
from app.schemas.tenant import AcceptInvitationRequest, InvitationInfoResponse
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.invitation_service import InvitationService
from app.services.oauth_service import OAuthService

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer()

DbDep = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[aioredis.Redis, Depends(get_redis)]

# -- Auth-check cache: forward-auth fires on every request to the guarded
#    upstream.  Identity is already cached (IDENTITY_CACHE_TTL=300s) by
#    IdentityResolver, so on cache-hit the remaining cost is 2 Redis GETs
#    (identity + tenant_status) + 1 Casbin enforce().  Caching the final
#    verdict eliminates even that for 30 s — enough to ride out concurrency
#    bursts from SPA static-file loads. --------------------------------------------------

_AUTH_CHECK_CACHE_PREFIX = "auth_check"
_AUTH_CHECK_CACHE_TTL = 30


def _audit_ctx(request: Request) -> dict[str, Any]:
    return {
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent"),
        "request_id": getattr(request.state, "request_id", None),
    }


@router.get("/config", response_model=BaseResponse[AuthConfigResponse])
async def auth_config() -> BaseResponse[AuthConfigResponse]:
    return BaseResponse(
        data=AuthConfigResponse(
            app_name=settings.APP_NAME,
            allow_user_registration=settings.ALLOW_USER_REGISTRATION,
            oidc_auto_redirect=settings.OIDC_AUTO_REDIRECT,
            enable_business_algorithm=settings.ENABLE_BUSINESS_ALGORITHM,
        ),
        message="获取成功",
    )


@router.post("/register", response_model=BaseResponse[TokenResponse])
async def register(
    req: RegisterRequest,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> BaseResponse[TokenResponse]:
    service = AuthService(db, redis)
    token = await service.register(req, audit_context=_audit_ctx(request))
    return BaseResponse(data=token, message="注册成功")


@router.post("/login", response_model=BaseResponse[TokenResponse])
async def login(
    req: LoginRequest,
    db: DbDep,
    redis: RedisDep,
    request: Request,
) -> BaseResponse[TokenResponse]:
    service = AuthService(db, redis)
    token = await service.login(req, audit_context=_audit_ctx(request))
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
    await service.logout(
        str(user.id), access_jti, refresh_jti, access_exp, refresh_exp, audit_context=_audit_ctx(request)
    )
    return BaseResponse(message="已退出登录")


def _build_user_response(user: UserModel) -> UserResponse:
    return UserResponse(
        id=str(user.id),
        username=user.username,
        email=user.email,
        nickname=user.nickname,
        avatar=user.avatar,
        is_active=user.is_active,
        role=user.role,
        auth_provider=user.auth_provider,
        tenant_id=str(user.tenant_id) if user.tenant_id else None,
    )


def _reject_external_account(user: UserModel) -> None:
    """第三方登录账号的资料与凭证由身份提供方统一管理, 禁止本地修改."""
    if user.auth_provider != "local":
        raise ForbiddenException("当前账号通过第三方登录, 相关信息由身份提供方统一管理, 无法修改")


@router.get("/me", response_model=BaseResponse[UserResponse])
async def me(user: CurrentUserEntity) -> BaseResponse[UserResponse]:
    return BaseResponse(data=_build_user_response(user), message="获取成功")


@router.get("/check", include_in_schema=False)
async def auth_check(
    request: Request,
    resource: Annotated[str, Query()],
    action: Annotated[str, Query()],
    db: DbDep,
    redis: RedisDep,
) -> Response:
    """APISIX forward-auth 通用鉴权端点.

    身份解析委托 ``resolve_identity_from_request`` (Cookie / Bearer),
    资源级鉴权走 Casbin ``enforce(role, resource, action)``.

    APISIX forward-auth 配置示例::

        {
          "forward-auth": {
            "uri": "http://backend.kubeai:8000/api/auth/check?resource=experiments&action=read",
            "request_headers": ["Cookie"],
            "upstream_headers": ["X-KubeAI-User"]
          }
        }
    """
    identity = await resolve_identity_from_request(request, db, redis)
    if not identity:
        raise UnauthorizedException("未登录或 Token 无效")
    if not identity.tenant_id:
        raise ForbiddenException("需要租户上下文")

    cache_key = f"{_AUTH_CHECK_CACHE_PREFIX}:{identity.id.hex}:{resource}:{action}"

    if redis is not None and await redis.get(cache_key) == b"1":
        return Response(status_code=200, headers={"X-KubeAI-User": identity.username})

    if not CasbinEnforcer.enforce(identity.role.value, resource, action):
        raise ForbiddenException(f"权限不足: 无法对 {resource} 执行 {action} 操作")

    if redis is not None:
        await redis.setex(cache_key, _AUTH_CHECK_CACHE_TTL, "1")

    return Response(status_code=200, headers={"X-KubeAI-User": identity.username})


@router.patch("/me/profile", response_model=BaseResponse[UserResponse])
async def update_profile(
    req: ProfileUpdateRequest,
    user: CurrentUserEntity,
    db: DbDep,
) -> BaseResponse[UserResponse]:
    _reject_external_account(user)
    if req.email is not None and req.email != user.email:
        existing = await db.execute(select(UserModel).where(UserModel.email == req.email, UserModel.id != user.id))
        if existing.scalar_one_or_none() is not None:
            raise ConflictException("该邮箱已被使用")
        user.email = req.email

    if req.nickname is not None:
        user.nickname = req.nickname

    await db.flush()
    return BaseResponse(data=_build_user_response(user), message="更新成功")


ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_AVATAR_SIZE = 2 * 1024 * 1024  # 2 MB


@router.post("/me/avatar", response_model=BaseResponse[UserResponse])
async def upload_avatar(
    user: CurrentUserEntity,
    db: DbDep,
    file: UploadFile = File(...),  # noqa: B008
) -> BaseResponse[UserResponse]:
    _reject_external_account(user)
    if file.content_type not in ALLOWED_AVATAR_TYPES:
        raise BadRequestException("仅支持 JPEG、PNG、GIF、WebP 格式的图片")
    content = await file.read()
    if len(content) > MAX_AVATAR_SIZE:
        raise BadRequestException("头像文件大小不能超过 2MB")
    b64 = base64.b64encode(content).decode()
    user.avatar = f"data:{file.content_type};base64,{b64}"
    await db.flush()
    return BaseResponse(data=_build_user_response(user), message="头像上传成功")


@router.post("/me/password", response_model=BaseResponse[None])
async def change_password(
    req: PasswordChangeRequest,
    user: CurrentUserEntity,
    db: DbDep,
) -> BaseResponse[None]:
    _reject_external_account(user)
    if not await verify_password(req.current_password, user.hashed_password):
        raise BadRequestException("当前密码错误")
    user.hashed_password = await hash_password(req.new_password)
    await db.flush()
    return BaseResponse(message="密码修改成功")


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
    request: Request,
    user: OptionalCurrentUser = None,
) -> BaseResponse[TokenResponse]:
    inv_service = InvitationService(db)
    auth_service = AuthService(db, redis)
    audit_ctx = _audit_ctx(request)

    if req.username and req.password:
        # 场景 A: 新用户注册 + 接受邀请
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
            hashed_password=await hash_password(req.password),
        )
        db.add(new_user)
        await db.flush()
        await db.refresh(new_user)

        await inv_service.accept_invitation(req.token, new_user.id)
        await db.refresh(new_user)

        audit_svc = AuditService(db)
        await audit_svc.log_action(
            action=AuditAction.ACCEPT_INVITE,
            resource_type=ResourceType.INVITATION,
            detail={"email": inv_info["email"], "role": inv_info["role"].value},
            user_id=new_user.id,
            tenant_id=new_user.tenant_id,
            **audit_ctx,
        )

        tokens = auth_service._generate_tokens(
            str(new_user.id),
            str(new_user.tenant_id) if new_user.tenant_id else None,
        )
        return BaseResponse(data=tokens, message="注册并加入租户成功")
    elif user:
        # 场景 B: 已登录用户接受邀请
        if user.tenant_id and not req.force:
            raise ConflictException("您当前已属于一个租户, 接受邀请将转移到新租户, 请确认操作")

        updated_user = await inv_service.accept_invitation(req.token, user.id)
        if not updated_user:
            raise BadRequestException("接受邀请失败")
        await db.refresh(updated_user)

        audit_svc = AuditService(db)
        await audit_svc.log_action(
            action=AuditAction.ACCEPT_INVITE,
            resource_type=ResourceType.INVITATION,
            detail={"email": updated_user.email},
            user_id=updated_user.id,
            tenant_id=updated_user.tenant_id,
            **audit_ctx,
        )

        tokens = auth_service._generate_tokens(
            str(updated_user.id),
            str(updated_user.tenant_id) if updated_user.tenant_id else None,
        )
        return BaseResponse(data=tokens, message="已加入租户")
    else:
        raise BadRequestException("请提供注册信息或先登录")
