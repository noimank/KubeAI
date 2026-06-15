from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.ws_pubsub import publish_status_changed
from app.integrations.k8s.dev_pod import get_dev_pod_manager
from app.integrations.k8s.namespace import make_namespace_name
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus
from app.models.tenant import Tenant

logger = structlog.get_logger(__name__)


async def check_and_cull_idle_environments(semaphore: asyncio.Semaphore | None = None) -> tuple[int, int]:
    """Stop RUNNING dev environments that have been idle longer than the timeout.

    Invoked by the taskiq-scheduled ``check_idle_dev_environments_task``.
    """
    timeout = timedelta(minutes=settings.DEV_ENV_IDLE_TIMEOUT_MINUTES)
    now = datetime.now(UTC)
    stopped_count = 0
    checked_count = 0
    guard = semaphore or asyncio.Semaphore(5)

    async with async_session_factory() as db:
        stmt = select(DevEnvironment).where(DevEnvironment.status == DevEnvironmentStatus.RUNNING)
        result = await db.execute(stmt)
        environments = list(result.scalars().all())
        checked_count = len(environments)

        pod_mgr = get_dev_pod_manager()

        # Batch-load tenants to avoid N individual queries
        tenant_ids = {env.tenant_id for env in environments}
        tenant_result = await db.execute(select(Tenant).where(Tenant.id.in_(tenant_ids)))
        tenant_map: dict[uuid.UUID, str] = {}
        for t in tenant_result.scalars().all():
            if isinstance(t, Tenant):
                ns = t.k8s_namespace_name or make_namespace_name(t.name)
                tenant_map[t.id] = ns

        for env in environments:
            async with guard:
                if env.status != DevEnvironmentStatus.RUNNING:
                    continue
                namespace = tenant_map.get(env.tenant_id)
                if not namespace:
                    continue
                try:
                    last_activity_str = await pod_mgr.get_pod_last_activity(env.id, namespace)
                except Exception:
                    logger.warning("idle_check_pod_error", env_id=str(env.id))
                    continue

                if last_activity_str is None:
                    continue

                last_activity = datetime.fromisoformat(last_activity_str)
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=UTC)

                created_at = env.created_at
                if created_at and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)
                reference_time = max(last_activity, created_at) if created_at else last_activity

                idle_duration = now - reference_time
                if idle_duration > timeout:
                    try:
                        # Set stopped_reason before deleting the pod so the
                        # K8s Pod Watcher picks up the correct reason on DELETED.
                        env.status = DevEnvironmentStatus.STOPPING
                        env.stopped_reason = "idle_timeout"
                        env.error_message = None
                        await db.commit()
                        await publish_status_changed(
                            env.tenant_id,
                            env.id,
                            DevEnvironmentStatus.RUNNING.value,
                            DevEnvironmentStatus.STOPPING.value,
                        )

                        await pod_mgr.stop_server(env.id, namespace)
                        stopped_count += 1
                        logger.info(
                            "env_auto_stopped_idle",
                            env_id=str(env.id),
                            env_name=env.name,
                            idle_minutes=int(idle_duration.total_seconds() / 60),
                        )
                    except Exception:
                        logger.exception("auto_stop_failed", env_id=str(env.id))

        if checked_count > 0:
            await db.commit()
            logger.info("idle_check_completed", checked=checked_count, stopped=stopped_count)

    return checked_count, stopped_count
