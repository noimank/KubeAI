from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.ws_pubsub import publish_ws_event
from app.integrations.k8s.dev_pod import get_dev_pod_manager
from app.integrations.k8s.namespace import make_namespace_name
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus

logger = structlog.get_logger(__name__)


class IdleChecker:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._semaphore = asyncio.Semaphore(5)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._check_loop())
            logger.info("idle_checker_started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("idle_checker_stopped")

    async def _check_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.DEV_ENV_IDLE_CHECK_INTERVAL_SECONDS)
                await self._check_and_cull_idle()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("idle_check_error")
                await asyncio.sleep(60)

    async def _check_and_cull_idle(self) -> None:
        await check_and_cull_idle_environments(self._semaphore)


async def check_and_cull_idle_environments(semaphore: asyncio.Semaphore | None = None) -> tuple[int, int]:
    timeout = timedelta(minutes=settings.DEV_ENV_IDLE_TIMEOUT_MINUTES)
    now = datetime.now(UTC)
    stopped_count = 0
    checked_count = 0
    guard = semaphore or asyncio.Semaphore(5)

    async with async_session_factory() as db:
        stmt = select(DevEnvironment).where(
            DevEnvironment.status.in_(
                [
                    DevEnvironmentStatus.RUNNING,
                ]
            )
        )
        result = await db.execute(stmt)
        environments = list(result.scalars().all())
        checked_count = len(environments)

        pod_mgr = get_dev_pod_manager()
        from app.models.tenant import Tenant

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
                        await pod_mgr.stop_server(env.id, namespace)
                        old_status = env.status
                        env.status = DevEnvironmentStatus.STOPPED
                        env.stopped_reason = "idle_timeout"
                        env.error_message = None
                        await publish_ws_event(
                            tenant_id=env.tenant_id,
                            event="dev_environment.status_changed",
                            payload={
                                "id": str(env.id),
                                "old_status": old_status,
                                "new_status": DevEnvironmentStatus.STOPPED.value,
                            },
                        )
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
            logger.info(
                "idle_check_completed",
                checked=checked_count,
                stopped=stopped_count,
            )

    return checked_count, stopped_count
