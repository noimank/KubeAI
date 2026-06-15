from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.taskiq_app import broker, interval_to_cron
from app.core.ws_pubsub import publish_ws_event
from app.services.dev_environment_service import DevEnvironmentService
from app.services.idle_checker import check_and_cull_idle_environments

logger = structlog.get_logger(__name__)


@broker.task(
    task_name="app.tasks.dev_environment.provision",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def provision_dev_environment_task(
    env_id: str,
    tenant_id: str,
    algorithm_id: str | None = None,
) -> dict[str, Any]:
    """First-time provisioning: create pod (tracking is handled by the K8s Pod Watcher)."""
    async with async_session_factory() as db:
        svc = DevEnvironmentService(db)
        await svc.provision_environment(
            uuid.UUID(env_id),
            uuid.UUID(tenant_id),
            algorithm_id=uuid.UUID(algorithm_id) if algorithm_id else None,
        )
    return {"env_id": env_id, "status": "provisioned"}


@broker.task(
    task_name="app.tasks.dev_environment.start",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def start_dev_environment_task(
    env_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Start a stopped dev environment: create pod (tracking is handled by the K8s Pod Watcher)."""
    async with async_session_factory() as db:
        svc = DevEnvironmentService(db)
        await svc.start_environment_async(uuid.UUID(env_id), uuid.UUID(tenant_id))
    return {"env_id": env_id, "status": "provisioned"}


@broker.task(
    task_name="app.tasks.dev_environment.stop",
    retry_on_error=True,
    max_retries=1,
)
async def stop_dev_environment_task(
    env_id: str,
    tenant_id: str,
    stopped_reason: str = "manual",
) -> dict[str, Any]:
    """Stop a running dev environment: delete pod + confirm STOPPED."""
    async with async_session_factory() as db:
        svc = DevEnvironmentService(db)
        try:
            await svc.stop_environment_async(
                uuid.UUID(env_id),
                uuid.UUID(tenant_id),
                stopped_reason=stopped_reason,
            )
        except Exception as exc:
            # Stop is best-effort on the pod side; the env may already be
            # terminating. The watchdog sync reconciles any stuck STOPPING.
            logger.warning("stop_dev_environment_error", env_id=env_id, error=str(exc))
            return {"env_id": env_id, "status": "error", "error": str(exc)}
    return {"env_id": env_id, "status": "stopped"}


@broker.task(
    task_name="app.tasks.dev_environment.delete",
    retry_on_error=True,
    max_retries=1,
)
async def delete_dev_environment_task(
    env_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """Delete a dev environment (pod + service + APISIX route + DB row)."""
    async with async_session_factory() as db:
        svc = DevEnvironmentService(db)
        try:
            await svc.delete_environment_async(uuid.UUID(env_id), uuid.UUID(tenant_id))
        except Exception as exc:
            logger.warning("delete_dev_environment_error", env_id=env_id, error=str(exc))
            return {"env_id": env_id, "status": "error", "error": str(exc)}

    # Notify frontend list/detail cache (row deleted, status_changed is meaningless)
    await publish_ws_event(
        tenant_id=uuid.UUID(tenant_id),
        event="dev_environment.deleted",
        payload={"id": env_id},
    )
    return {"env_id": env_id, "status": "deleted"}


@broker.task(
    task_name="app.tasks.dev_environment.check_idle",
    schedule=[{"cron": interval_to_cron(settings.DEV_ENV_IDLE_CHECK_INTERVAL_SECONDS)}],
)
async def check_idle_dev_environments_task() -> dict[str, Any]:
    """Periodically check and cull idle dev environments."""
    checked_count, stopped_count = await check_and_cull_idle_environments()
    return {"checked_count": checked_count, "stopped_count": stopped_count}


async def enqueue_dev_environment_provision(
    env_id: uuid.UUID,
    tenant_id: uuid.UUID,
    algorithm_id: uuid.UUID | None = None,
) -> None:
    """Enqueue a dev environment provisioning task (called from API endpoint)."""
    await provision_dev_environment_task.kiq(
        str(env_id),
        str(tenant_id),
        str(algorithm_id) if algorithm_id else None,
    )


async def enqueue_dev_environment_start(env_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Enqueue a dev environment start task (called from API endpoint)."""
    await start_dev_environment_task.kiq(str(env_id), str(tenant_id))


async def enqueue_dev_environment_stop(
    env_id: uuid.UUID,
    tenant_id: uuid.UUID,
    stopped_reason: str = "manual",
) -> None:
    """Enqueue a dev environment stop task (called from API endpoint)."""
    await stop_dev_environment_task.kiq(str(env_id), str(tenant_id), stopped_reason)


async def enqueue_dev_environment_delete(env_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """Enqueue a dev environment delete task (called from API endpoint)."""
    await delete_dev_environment_task.kiq(str(env_id), str(tenant_id))
