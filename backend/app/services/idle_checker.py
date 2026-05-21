from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.integrations.jupyterhub.client import get_jupyterhub_client
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
        timeout = timedelta(minutes=settings.DEV_ENV_IDLE_TIMEOUT_MINUTES)
        now = datetime.now(UTC)
        stopped_count = 0
        checked_count = 0

        async with async_session_factory() as db:
            stmt = select(DevEnvironment).where(
                DevEnvironment.status.in_(
                    [
                        DevEnvironmentStatus.RUNNING,
                        DevEnvironmentStatus.CREATING,
                    ]
                )
            )
            result = await db.execute(stmt)
            environments = list(result.scalars().all())
            checked_count = len(environments)

            jh_client = get_jupyterhub_client()

            for env in environments:
                async with self._semaphore:
                    jh_user = env.jupyterhub_user
                    if not jh_user:
                        continue
                    try:
                        last_activity_str = await jh_client.get_server_last_activity(jh_user)
                    except Exception:
                        logger.warning("idle_check_jh_error", env_id=str(env.id))
                        continue

                    if last_activity_str is None:
                        continue

                    last_activity = datetime.fromisoformat(last_activity_str)
                    if last_activity.tzinfo is None:
                        last_activity = last_activity.replace(tzinfo=UTC)

                    idle_duration = now - last_activity
                    if idle_duration > timeout:
                        try:
                            await jh_client.stop_server(jh_user)
                            env.status = DevEnvironmentStatus.STOPPED
                            env.stopped_reason = "idle_timeout"
                            env.error_message = None
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
