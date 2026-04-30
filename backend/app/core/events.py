import structlog

from app.core.casbin import CasbinEnforcer
from app.core.config import settings
from app.core.database import close_db
from app.core.redis import close_redis, init_redis
from app.integrations.minio import MinIOClient

logger = structlog.get_logger()

minio_client: MinIOClient | None = None


def get_minio_client() -> MinIOClient:
    if minio_client is None:
        raise RuntimeError("MinIO client not initialized")
    return minio_client


async def on_startup() -> None:
    global minio_client
    await init_redis()
    CasbinEnforcer.initialize(settings.DATABASE_URL)
    minio_client = MinIOClient()
    logger.info("application_startup", app="KubeAI")


async def on_shutdown() -> None:
    await close_db()
    await close_redis()
    logger.info("application_shutdown", app="KubeAI")
