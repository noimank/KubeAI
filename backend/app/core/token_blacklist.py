import redis.asyncio as aioredis
import structlog

logger = structlog.get_logger()

BLACKLIST_PREFIX = "token_blacklist"


class TokenBlacklistService:
    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis

    async def revoke_token(self, jti: str, expires_in: int) -> None:
        key = f"{BLACKLIST_PREFIX}:{jti}"
        await self.redis.setex(key, expires_in, "revoked")
        logger.info("token_revoked", jti=jti, expires_in=expires_in)

    async def is_revoked(self, jti: str) -> bool:
        key = f"{BLACKLIST_PREFIX}:{jti}"
        return bool(await self.redis.exists(key))

    async def revoke_all_user_tokens(self, user_id: str) -> None:
        version_key = f"user_token_version:{user_id}"
        await self.redis.incr(version_key)
        logger.info("all_user_tokens_revoked", user_id=user_id)
