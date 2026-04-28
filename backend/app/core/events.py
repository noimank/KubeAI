import structlog

from app.core.casbin import CasbinEnforcer
from app.core.config import settings
from app.core.database import close_db
from app.core.redis import close_redis, init_redis

logger = structlog.get_logger()


async def on_startup() -> None:
    await init_redis()
    CasbinEnforcer.initialize(settings.DATABASE_URL)
    logger.info("application_startup", app="KubeAI")


async def on_shutdown() -> None:
    await close_db()
    await close_redis()
    logger.info("application_shutdown", app="KubeAI")
