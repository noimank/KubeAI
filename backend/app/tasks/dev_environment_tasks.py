from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.taskiq_app import _interval_to_cron, broker
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus
from app.services.dev_environment_service import DevEnvironmentService
from app.services.idle_checker import check_and_cull_idle_environments

logger = structlog.get_logger(__name__)


async def _mark_retrying(env_id: str, tenant_id: str, error: str) -> None:
    async with async_session_factory() as db:
        result = await db.execute(
            select(DevEnvironment).where(
                DevEnvironment.id == uuid.UUID(env_id),
                DevEnvironment.tenant_id == uuid.UUID(tenant_id),
            )
        )
        env = result.scalar_one_or_none()
        if env is None or env.status == DevEnvironmentStatus.STOPPED:
            return
        env.status = DevEnvironmentStatus.PENDING
        env.error_message = f"启动失败, 正在重试: {error}"
        await db.commit()


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
    """创建开发环境 (async-native, 由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = DevEnvironmentService(db)
            await svc.provision_environment(
                uuid.UUID(env_id),
                uuid.UUID(tenant_id),
                algorithm_id=uuid.UUID(algorithm_id) if algorithm_id else None,
            )
    except Exception as exc:
        logger.warning("provision_dev_environment_error", env_id=env_id, error=str(exc))
        await _mark_retrying(env_id, tenant_id, str(exc))
        raise

    return {"env_id": env_id, "status": "submitted"}


@broker.task(
    task_name="app.tasks.dev_environment.sync_statuses",
    schedule=[{"cron": _interval_to_cron(settings.DEV_ENV_STATUS_SYNC_INTERVAL_SECONDS)}],
)
async def sync_dev_environment_statuses_task(limit: int = 200) -> dict[str, Any]:
    """定时同步非终态开发环境的 JupyterHub 状态."""
    async with async_session_factory() as db:
        svc = DevEnvironmentService(db)
        synced_count = await svc.sync_non_terminal_environments(limit=limit)

    return {"synced_count": synced_count}


@broker.task(
    task_name="app.tasks.dev_environment.check_idle",
    schedule=[{"cron": _interval_to_cron(settings.DEV_ENV_IDLE_CHECK_INTERVAL_SECONDS)}],
)
async def check_idle_dev_environments_task() -> dict[str, Any]:
    """定时检查并回收空闲开发环境."""
    checked_count, stopped_count = await check_and_cull_idle_environments()
    return {"checked_count": checked_count, "stopped_count": stopped_count}


async def enqueue_dev_environment_provision(
    env_id: uuid.UUID,
    tenant_id: uuid.UUID,
    algorithm_id: uuid.UUID | None = None,
) -> None:
    """将开发环境创建任务入队 (从 API endpoint 调用)."""
    await provision_dev_environment_task.kiq(
        str(env_id),
        str(tenant_id),
        str(algorithm_id) if algorithm_id else None,
    )
