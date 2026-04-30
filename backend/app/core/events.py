import structlog
from sqlalchemy import select

from app.core.casbin import CasbinEnforcer
from app.core.config import settings
from app.core.database import async_session_factory, close_db
from app.core.redis import close_redis, init_redis
from app.core.security import hash_password
from app.integrations.minio import MinIOClient
from app.models.enums import TenantStatus, UserRole
from app.models.tenant import Tenant
from app.models.user import User

logger = structlog.get_logger()

minio_client: MinIOClient | None = None


def get_minio_client() -> MinIOClient:
    if minio_client is None:
        raise RuntimeError("MinIO client not initialized")
    return minio_client


async def _init_admin_user() -> None:
    async with async_session_factory() as session:
        stmt = select(User).where(User.username == "admin")
        result = await session.execute(stmt)
        admin = result.scalar_one_or_none()
        if admin is not None:
            return

        tenant_result = await session.execute(select(Tenant).where(Tenant.name == "default"))
        tenant = tenant_result.scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                name="default",
                display_name="默认租户",
                description="系统自动创建的默认租户",
                status=TenantStatus.ACTIVE,
            )
            session.add(tenant)
            await session.flush()

        admin = User(
            username="admin",
            email="admin@163.com",
            hashed_password=hash_password("Admin123456"),
            role=UserRole.ADMIN,
            is_active=True,
            tenant_id=tenant.id,
        )
        session.add(admin)
        await session.commit()
        logger.info("admin_user_created", username="admin")


async def on_startup() -> None:
    global minio_client
    await init_redis()
    CasbinEnforcer.initialize(settings.DATABASE_URL)
    await _init_admin_user()
    minio_client = MinIOClient()
    logger.info("application_startup", app="KubeAI")


async def on_shutdown() -> None:
    await close_db()
    await close_redis()
    logger.info("application_shutdown", app="KubeAI")
