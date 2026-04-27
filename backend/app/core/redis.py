from collections.abc import AsyncGenerator

import redis.asyncio as aioredis

from app.core.config import settings

_redis_pool: aioredis.Redis | None = None


async def init_redis() -> None:
    global _redis_pool
    _redis_pool = aioredis.from_url(
        settings.REDIS_URL,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
        decode_responses=True,
    )


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    if _redis_pool is None:
        await init_redis()
    assert _redis_pool is not None
    yield _redis_pool


async def close_redis() -> None:
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None
