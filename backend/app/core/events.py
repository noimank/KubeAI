import asyncio

import structlog
from sqlalchemy import select

from app.core.casbin import CasbinEnforcer
from app.core.config import settings
from app.core.database import async_session_factory, close_db
from app.core.redis import _redis_pool, close_redis, init_redis
from app.core.security import hash_password
from app.core.ws_manager import ConnectionManager, set_ws_manager
from app.core.ws_pubsub import WebSocketPubSub, set_ws_pubsub
from app.integrations.harbor.client import HarborClient
from app.integrations.jupyterhub.client import close_jupyterhub_client
from app.integrations.k8s.client import close_k8s_clients
from app.integrations.labelstudio import LabelStudioClient
from app.integrations.minio import MinIOClient
from app.integrations.mlflow.client import MLflowClient
from app.integrations.prometheus.client import PrometheusClient
from app.models.enums import TenantStatus, UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.services.idle_checker import IdleChecker

logger = structlog.get_logger()

minio_client: MinIOClient | None = None
harbor_client: HarborClient | None = None
prometheus_client: PrometheusClient | None = None
labelstudio_client: LabelStudioClient | None = None
mlflow_client: MLflowClient | None = None
idle_checker: IdleChecker | None = None
_metrics_push_task: asyncio.Task[None] | None = None


def get_minio_client() -> MinIOClient:
    if minio_client is None:
        raise RuntimeError("MinIO client not initialized")
    return minio_client


def get_harbor_client() -> HarborClient:
    if harbor_client is None:
        raise RuntimeError("Harbor client not initialized")
    return harbor_client


def get_prometheus_client() -> PrometheusClient | None:
    return prometheus_client


def get_labelstudio_client() -> LabelStudioClient:
    if labelstudio_client is None:
        raise RuntimeError("LabelStudio 客户端未初始化")
    return labelstudio_client


def get_mlflow_client() -> MLflowClient | None:
    return mlflow_client


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
    global minio_client, prometheus_client, labelstudio_client
    global harbor_client, mlflow_client, idle_checker
    await init_redis()
    CasbinEnforcer.initialize(settings.DATABASE_URL)
    await _init_admin_user()

    # WebSocket infrastructure
    ws_manager = ConnectionManager()
    set_ws_manager(ws_manager)
    if _redis_pool is not None:
        ws_pubsub = WebSocketPubSub(_redis_pool)
        set_ws_pubsub(ws_pubsub)
        await ws_pubsub.subscribe()
    else:
        set_ws_pubsub(None)

    minio_client = MinIOClient()
    harbor_client = HarborClient()
    if settings.PROMETHEUS_URL:
        prometheus_client = PrometheusClient()
    if settings.LABEL_STUDIO_API_TOKEN:
        labelstudio_client = LabelStudioClient()
    if settings.MLFLOW_ENABLED:
        mlflow_client = MLflowClient()
    idle_checker = IdleChecker()
    idle_checker.start()

    # Start cluster metrics push background task
    global _metrics_push_task
    _metrics_push_task = asyncio.create_task(_metrics_push_loop())

    logger.info("application_startup", app="KubeAI")


async def on_shutdown() -> None:
    global prometheus_client, labelstudio_client, harbor_client, minio_client, mlflow_client
    global idle_checker, _metrics_push_task

    if _metrics_push_task:
        _metrics_push_task.cancel()
        _metrics_push_task = None

    from app.core.ws_pubsub import get_ws_pubsub

    ws_pubsub = get_ws_pubsub()
    if ws_pubsub:
        await ws_pubsub.close()
        set_ws_pubsub(None)

    if idle_checker:
        await idle_checker.stop()
        idle_checker = None
    if prometheus_client:
        await prometheus_client.close()
        prometheus_client = None
    if labelstudio_client:
        await labelstudio_client.close()
        labelstudio_client = None
    if harbor_client:
        await harbor_client.close()
        harbor_client = None
    if minio_client:
        minio_client.close()
        minio_client = None
    if mlflow_client:
        await mlflow_client.close()
        mlflow_client = None
    await close_jupyterhub_client()
    await close_k8s_clients()
    await close_db()
    await close_redis()
    logger.info("application_shutdown", app="KubeAI")
