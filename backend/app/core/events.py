import asyncio

import structlog
from sqlalchemy import select

from app.core.casbin import CasbinEnforcer
from app.core.clients import close_clients, init_clients
from app.core.config import settings
from app.core.database import async_session_factory, close_db
from app.core.security import hash_password
from app.core.ws_manager import ConnectionManager, set_ws_manager
from app.core.ws_pubsub import WebSocketPubSub, set_ws_pubsub
from app.integrations.k8s.client import close_k8s_clients
from app.models.enums import TenantStatus, UserRole
from app.models.tenant import Tenant
from app.models.user import User

logger = structlog.get_logger()

_metrics_push_task: asyncio.Task[None] | None = None

# Re-export client getters for backward compatibility — prefer importing from
# ``app.core.clients`` directly in new code.
from app.core.clients import (  # noqa: E402, F401
    get_harbor_client,
    get_labelstudio_client,
    get_minio_client,
    get_mlflow_client,
    get_prometheus_client,
)


async def _init_admin_user() -> None:
    async with async_session_factory() as session:
        # Ensure default tenant exists
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

        # Ensure K8s namespace for default tenant
        if not tenant.k8s_namespace_name:
            await _ensure_default_tenant_k8s(tenant)

        # Ensure admin user exists
        stmt = select(User).where(User.username == "admin")
        result = await session.execute(stmt)
        if result.scalar_one_or_none() is None:
            session.add(
                User(
                    username="admin",
                    email="admin@163.com",
                    hashed_password=await hash_password("Admin123456"),
                    role=UserRole.ADMIN,
                    is_active=True,
                    tenant_id=tenant.id,
                )
            )
            logger.info("admin_user_created", username="admin")

        await session.commit()


async def _ensure_default_tenant_k8s(tenant: Tenant) -> None:
    from app.integrations.k8s.namespace import create_namespace, make_namespace_name, tenant_namespace_labels
    from app.services.tenant_service import TenantService

    namespace = make_namespace_name(tenant.name)
    try:
        await create_namespace(namespace, labels=tenant_namespace_labels())
        await TenantService.ensure_tenant_k8s_infra(
            namespace,
            gpu_limit=tenant.gpu_limit,
            cpu_limit=tenant.cpu_limit,
            memory_limit=tenant.memory_limit,
            storage_limit=tenant.storage_limit,
        )
        tenant.k8s_namespace_name = namespace
        logger.info("default_tenant_namespace_ready", namespace=namespace)
    except Exception as e:
        logger.warning("default_tenant_namespace_failed", error=str(e))


async def _metrics_push_loop() -> None:
    """Periodically push cluster resource metrics via WebSocket (every 30s)."""
    await asyncio.sleep(10)  # Wait for startup to complete
    while True:
        try:
            from app.services.monitoring_service import push_cluster_metrics

            await push_cluster_metrics()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("metrics_push_loop_error")
        await asyncio.sleep(30)


async def on_startup() -> None:
    global _metrics_push_task

    await init_clients()
    CasbinEnforcer.initialize(settings.DATABASE_URL)
    await _init_admin_user()

    # WebSocket infrastructure
    ws_manager = ConnectionManager()
    set_ws_manager(ws_manager)

    from app.core.redis import _redis_pool

    if _redis_pool is not None:
        ws_pubsub = WebSocketPubSub(_redis_pool)
        set_ws_pubsub(ws_pubsub)
        await ws_pubsub.subscribe()
    else:
        set_ws_pubsub(None)

    # Start cluster metrics push background task
    _metrics_push_task = asyncio.create_task(_metrics_push_loop())

    logger.info("application_startup", app="KubeAI")


async def on_shutdown() -> None:
    global _metrics_push_task

    if _metrics_push_task:
        _metrics_push_task.cancel()
        _metrics_push_task = None

    from app.core.ws_pubsub import get_ws_pubsub

    ws_pubsub = get_ws_pubsub()
    if ws_pubsub:
        await ws_pubsub.close()
        set_ws_pubsub(None)

    await close_k8s_clients()
    await close_clients()
    await close_db()
    logger.info("application_shutdown", app="KubeAI")
