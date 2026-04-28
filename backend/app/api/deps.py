from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as aioredis
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.exceptions import ForbiddenException, UnauthorizedException
from app.core.redis import get_redis
from app.core.security import decode_token
from app.core.token_blacklist import TokenBlacklistService
from app.models.user import User

security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),  # noqa: B008
    db: AsyncSession = Depends(get_db),  # noqa: B008
    redis: aioredis.Redis = Depends(get_redis),  # noqa: B008
) -> User:
    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise UnauthorizedException("无效或过期的 Token") from None

    if payload.get("type") != "access":
        raise UnauthorizedException("无效的 Token 类型")

    jti = payload.get("jti")
    if not jti:
        raise UnauthorizedException("无效的 Token")

    blacklist = TokenBlacklistService(redis)
    if await blacklist.is_revoked(jti):
        raise UnauthorizedException("Token 已被吊销")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException("无效的 Token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException("用户不存在")
    if not user.is_active:
        raise ForbiddenException("用户已被禁用")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
