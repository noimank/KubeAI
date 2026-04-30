from __future__ import annotations

import json
import secrets
from typing import TYPE_CHECKING, cast

import httpx
import structlog
from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore[import-untyped]
from sqlalchemy import select

from app.core.config import settings
from app.core.exceptions import ExternalServiceException, UnauthorizedException
from app.core.security import create_access_token, create_refresh_token, hash_password
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.oauth import OAuthProviderResponse

if TYPE_CHECKING:
    import redis.asyncio as aioredis
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger()

STATE_TTL = 600
DISCOVERY_CACHE_TTL = 3600


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
            await client.fetch_token(
                discovery["token_endpoint"],
                code=code,
                state=state,
                redirect_uri=redirect_uri,
            )

            userinfo_resp = await client.get(discovery["userinfo_endpoint"])
            if userinfo_resp.status_code != 200:
                raise ExternalServiceException("无法获取用户信息")
            userinfo = userinfo_resp.json()

        external_id = str(userinfo.get("sub"))
        email = userinfo.get("email", "")
        preferred_username = userinfo.get("preferred_username") or (email.split("@")[0] if email else external_id)

        user = await self._find_or_create_user(external_id, preferred_username, email)
        return self._generate_tokens(str(user.id), str(user.tenant_id) if user.tenant_id else None)

    async def _find_or_create_user(self, external_id: str, username: str, email: str) -> User:
        result = await self.db.execute(
            select(User).where(User.auth_provider == "oidc", User.external_id == external_id)
        )
        user = result.scalar_one_or_none()
        if user:
            return user

        if not username:
            username = external_id
        if not email:
            email = f"{username}@oauth.local"

        base_username = username
        counter = 1
        while True:
            existing = await self.db.execute(select(User).where(User.username == username))
            if existing.scalar_one_or_none() is None:
                break
            username = f"{base_username}_{counter}"
            counter += 1

        if email:
            existing = await self.db.execute(select(User).where(User.email == email))
            if existing.scalar_one_or_none() is not None:
                email = f"{username}@oauth.local"

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            auth_provider="oidc",
            external_id=external_id,
        )
        self.db.add(user)
        await self.db.flush()

        logger.info("oauth_user_created", user_id=str(user.id), username=username)
        return user

    def _generate_tokens(self, user_id: str, tenant_id: str | None = None) -> TokenResponse:
        payload: dict[str, str] = {"sub": user_id}
        if tenant_id is not None:
            payload["tenant_id"] = tenant_id
        return TokenResponse(
            access_token=create_access_token(payload),
            refresh_token=create_refresh_token(payload),
            tenant_id=tenant_id,
        )
