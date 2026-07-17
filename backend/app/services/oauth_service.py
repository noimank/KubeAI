from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, cast

import httpx
import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore[import-untyped]
from sqlalchemy import func, select

from app.core.config import settings
from app.core.exceptions import ExternalServiceException, UnauthorizedException
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.oauth import OAuthProviderResponse

if TYPE_CHECKING:
    import uuid

    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

STATE_TTL = 600
DISCOVERY_CACHE_TTL = 3600

_ROLE_PRIORITY: dict[UserRole, int] = {
    UserRole.ADMIN: 100,
    UserRole.MLOPS: 75,
    UserRole.ENGINEER: 50,
    UserRole.ANNOTATOR: 25,
}


class OAuthService:
    def __init__(self, db: AsyncSession, redis: aioredis.Redis):
        self.db = db
        self.redis = redis

    def get_providers(self) -> list[OAuthProviderResponse]:
        if not settings.OIDC_ENABLED:
            return []
        return [OAuthProviderResponse(name="oidc", display_name=settings.OIDC_DISPLAY_NAME)]

    async def _get_discovery(self) -> dict[str, str]:
        cache_key = f"oidc:discovery:{settings.OIDC_ISSUER}"
        cached = await self.redis.get(cache_key)
        if cached:
            return cast("dict[str, str]", json.loads(cached))

        url = f"{settings.OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration"
        async with httpx.AsyncClient() as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                raise ExternalServiceException(f"无法获取 OIDC Discovery: {url}")
            doc = resp.json()

        await self.redis.setex(cache_key, DISCOVERY_CACHE_TTL, json.dumps(doc))
        return cast("dict[str, str]", doc)

    async def get_authorization_url(self, redirect_uri: str) -> tuple[str, str]:
        discovery = await self._get_discovery()
        state = secrets.token_urlsafe(32)

        await self.redis.setex(f"oauth:state:{state}", STATE_TTL, "oidc")

        async with AsyncOAuth2Client(
            settings.OIDC_CLIENT_ID,
            settings.OIDC_CLIENT_SECRET,
            scope=settings.OIDC_SCOPES,
        ) as client:
            authorization_url, _ = client.create_authorization_url(
                discovery["authorization_endpoint"],
                redirect_uri=redirect_uri,
                state=state,
            )

        return authorization_url, state

    async def handle_callback(self, code: str, state: str, redirect_uri: str) -> TokenResponse:
        cached = await self.redis.get(f"oauth:state:{state}")
        if not cached:
            raise UnauthorizedException("无效或已过期的 state 参数")
        await self.redis.delete(f"oauth:state:{state}")

        discovery = await self._get_discovery()

        async with AsyncOAuth2Client(
            settings.OIDC_CLIENT_ID,
            settings.OIDC_CLIENT_SECRET,
            scope=settings.OIDC_SCOPES,
        ) as client:
            token = await client.fetch_token(
                discovery["token_endpoint"],
                code=code,
                state=state,
                redirect_uri=redirect_uri,
            )

            access_token = token.get("access_token")

            userinfo_resp = await client.get(discovery["userinfo_endpoint"])
            if userinfo_resp.status_code != 200:
                raise ExternalServiceException("无法获取用户信息")
            userinfo = userinfo_resp.json()

            # Casdoor: /api/userinfo excludes roles. Fetch them via /api/get-account.
            if access_token:
                try:
                    account_url = f"{settings.OIDC_ISSUER.rstrip('/')}/api/get-account"
                    account_resp = await client.get(
                        account_url,
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    if account_resp.status_code == 200:
                        account_data = account_resp.json().get("data", {})
                        raw_roles = account_data.get("roles") or []
                        # Roles from /api/get-account are objects with "name" field
                        role_names = [r["name"] if isinstance(r, dict) else str(r) for r in raw_roles]
                        if role_names:
                            userinfo["roles"] = role_names
                            logger.info("oidc_roles_from_casdoor", roles=role_names)
                except Exception:
                    logger.warning("oidc_get_account_failed", exc_info=True)

        sub = userinfo.get("sub")
        if not sub:
            raise UnauthorizedException("OIDC 用户信息缺少 sub")

        external_id = str(sub)
        email = str(userinfo.get("email") or "")
        preferred_username = str(userinfo.get("preferred_username") or (email.split("@")[0] if email else external_id))
        nickname = (
            str(v) if (v := userinfo.get("displayName") or userinfo.get("nickname") or userinfo.get("name")) else None
        )

        role = self._extract_role_from_userinfo(userinfo)

        user = await self._find_or_create_user(external_id, preferred_username, email, nickname, role=role)
        return self._generate_tokens(str(user.id), str(user.tenant_id) if user.tenant_id else None)

    async def _restore_if_deleted(self, user: User) -> bool:
        if user.deleted_at is None:
            return False
        user.deleted_at = None
        user.is_active = True
        logger.info("oauth_user_restored", user_id=str(user.id), username=user.username)
        return True

    async def _find_or_create_user(
        self,
        external_id: str,
        username: str,
        email: str,
        nickname: str | None = None,
        role: UserRole | None = None,
    ) -> User:
        username = self._normalize_username(username or external_id)
        email = email.strip()

        result = await self.db.execute(
            select(User).where(User.auth_provider == "oidc", User.external_id == external_id)
        )
        user = result.scalar_one_or_none()
        if user:
            await self._restore_if_deleted(user)
            await self._sync_oauth_profile(user, username, email, nickname, role=role)
            return user

        if email:
            existing_email = await self._find_user_by_email(email)
            if existing_email:
                existing_email.auth_provider = "oidc"
                existing_email.external_id = external_id
                await self._restore_if_deleted(existing_email)
                await self._sync_oauth_profile(existing_email, username, email, nickname, role=role)
                logger.info("oauth_user_bound", user_id=str(existing_email.id), username=existing_email.username)
                return existing_email

        username = await self._make_unique_username(username)
        email = await self._make_unique_email(email, username)

        default_tenant_id = await self._get_default_tenant_id()

        user = User(
            username=username,
            email=email,
            nickname=nickname,
            hashed_password=await hash_password("Kubeai#123456"),
            auth_provider="oidc",
            external_id=external_id,
            tenant_id=default_tenant_id,
            role=role if role is not None else UserRole.ENGINEER,
        )
        self.db.add(user)
        await self.db.flush()

        logger.info(
            "oauth_user_created",
            user_id=str(user.id),
            username=username,
            tenant_id=str(default_tenant_id) if default_tenant_id else None,
        )
        return user

    def _normalize_username(self, username: str) -> str:
        username = username.strip()
        if not username:
            return "oidc_user"
        return username[:50]

    def _username_with_suffix(self, base_username: str, counter: int) -> str:
        suffix = f"_{counter}"
        return f"{base_username[: 50 - len(suffix)]}{suffix}"

    async def _make_unique_username(self, username: str, current_user: User | None = None) -> str:
        base_username = self._normalize_username(username)
        candidate = base_username
        counter = 1
        while True:
            existing = await self.db.execute(select(User).where(User.username == candidate))
            existing_user = existing.scalar_one_or_none()
            if existing_user is None or (current_user is not None and existing_user.id == current_user.id):
                return candidate
            candidate = self._username_with_suffix(base_username, counter)
            counter += 1

    async def _find_user_by_email(self, email: str) -> User | None:
        if not email:
            return None
        result = await self.db.execute(select(User).where(func.lower(User.email) == email.lower()))
        return result.scalar_one_or_none()

    async def _make_unique_email(self, email: str, username: str, current_user: User | None = None) -> str:
        candidate = (email.strip() or f"{username}@oauth.local")[:255]
        counter = 1
        while True:
            existing_user = await self._find_user_by_email(candidate)
            if existing_user is None or (current_user is not None and existing_user.id == current_user.id):
                return candidate
            suffix = f"_{counter}"
            local_part = username[: 255 - len("@oauth.local") - len(suffix)]
            candidate = f"{local_part}{suffix}@oauth.local"
            counter += 1

    @staticmethod
    def _extract_role_from_userinfo(userinfo: dict[str, object]) -> UserRole | None:
        """Extract the highest-priority KubeAI role from OIDC userinfo.

        Reads the "roles" claim, filters for entries with "kubeai_" prefix,
        strips the prefix, maps to UserRole enum, and returns the highest-priority
        role. Returns None if no matching role is found.
        """
        roles = userinfo.get("roles", [])
        if not isinstance(roles, list) or not roles:
            return None

        mapped: list[UserRole] = []
        for r in roles:
            if not isinstance(r, str) or not r.startswith("kubeai_"):
                continue
            role_name = r.removeprefix("kubeai_")
            try:
                mapped.append(UserRole(role_name))
            except ValueError:
                logger.warning("oidc_unknown_role", raw_role=r, stripped=role_name)

        if not mapped:
            logger.info("oidc_roles_no_kubeai_match", roles=roles)
            return None

        mapped.sort(key=lambda r: _ROLE_PRIORITY[r], reverse=True)
        selected = mapped[0]
        logger.info("oidc_role_selected", selected=selected.value)
        return selected

    async def _sync_oauth_profile(
        self,
        user: User,
        username: str,
        email: str,
        nickname: str | None = None,
        role: UserRole | None = None,
    ) -> None:
        if username and user.username != username:
            user.username = await self._make_unique_username(username, current_user=user)

        if email and user.email != email:
            email = email[:255]
            existing_user = await self._find_user_by_email(email)
            if existing_user is None or existing_user.id == user.id:
                user.email = email

        if nickname:
            user.nickname = nickname[:100]

        if role is not None and user.role != role:
            old_role = user.role
            user.role = role
            logger.info(
                "oauth_role_synced",
                user_id=str(user.id),
                username=user.username,
                old_role=old_role.value,
                new_role=role.value,
            )

    async def _get_default_tenant_id(self) -> uuid.UUID | None:
        result = await self.db.execute(select(Tenant).where(Tenant.name == "default"))
        tenant = result.scalar_one_or_none()
        return tenant.id if tenant else None

    def _generate_tokens(self, user_id: str, tenant_id: str | None = None) -> TokenResponse:
        payload: dict[str, str] = {"sub": user_id}
        if tenant_id is not None:
            payload["tenant_id"] = tenant_id
        return TokenResponse(
            access_token=create_access_token(payload),
            refresh_token=create_refresh_token(payload),
            tenant_id=tenant_id,
        )
