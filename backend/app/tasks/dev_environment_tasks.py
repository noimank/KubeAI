from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.taskiq_app import broker, interval_to_cron
from app.core.ws_pubsub import publish_ws_event
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus
from app.services.dev_environment_service import DevEnvironmentService
from app.services.idle_checker import check_and_cull_idle_environments

logger = structlog.get_logger(__name__)


async def _publish_status_change(
    env_id: uuid.UUID,
    tenant_id: uuid.UUID,
    old_status: str,
    new_status: str,
) -> None:
    if old_status == new_status:
        return
    await publish_ws_event(
        tenant_id=tenant_id,
        event="dev_environment.status_changed",
        payload={"id": str(env_id), "old_status": old_status, "new_status": new_status},
    )


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
        old_status = env.status
        env.status = DevEnvironmentStatus.PENDING
        env.error_message = f"启动失败, 正在重试: {error}"
        await db.commit()
        if old_status != env.status:
            await publish_ws_event(
                tenant_id=env.tenant_id,
                event="dev_environment.status_changed",
                payload={"id": str(env.id), "old_status": old_status, "new_status": env.status},
            )


async def _mark_failed(env_id: str, tenant_id: str, error: str) -> None:
    """task 重试用尽后置 FAILED 并发 WS 事件."""
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
        old_status = env.status
        env.status = DevEnvironmentStatus.FAILED
        env.error_message = error
        await db.commit()
        if old_status != env.status:
            await publish_ws_event(
                tenant_id=env.tenant_id,
                event="dev_environment.status_changed",
                payload={"id": str(env.id), "old_status": old_status, "new_status": env.status},
            )


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
    task_name="app.tasks.dev_environment.start",
    retry_on_error=True,
    max_retries=settings.TASK_MAX_RETRIES,
)
async def start_dev_environment_task(
    env_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """启动开发环境 (async-native, 由 Taskiq worker 执行)."""
    try:
        async with async_session_factory() as db:
            svc = DevEnvironmentService(db)
            await svc.start_environment_async(uuid.UUID(env_id), uuid.UUID(tenant_id))
    except Exception as exc:
        logger.warning("start_dev_environment_error", env_id=env_id, error=str(exc))
        await _mark_failed(env_id, tenant_id, f"启动失败: {exc}")
        raise

    return {"env_id": env_id, "status": "submitted"}


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
    """停止开发环境 (async-native, 由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        svc = DevEnvironmentService(db)
        try:
            await svc.stop_environment_async(
                uuid.UUID(env_id),
                uuid.UUID(tenant_id),
                stopped_reason=stopped_reason,
            )
        except Exception as exc:
            logger.warning("stop_dev_environment_error", env_id=env_id, error=str(exc))
            # stop 失败不能静默: 标记 FAILED 并推 WS 事件, 让前端从"停止中"过渡态中恢复
            await _mark_failed(env_id, tenant_id, f"停止失败: {exc}")
            return {"env_id": env_id, "status": "error", "error": str(exc)}

    return {"env_id": env_id, "status": "submitted"}


@broker.task(
    task_name="app.tasks.dev_environment.delete",
    retry_on_error=True,
    max_retries=1,
)
async def delete_dev_environment_task(
    env_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """删除开发环境 (async-native, 由 Taskiq worker 执行)."""
    async with async_session_factory() as db:
        svc = DevEnvironmentService(db)
        try:
            await svc.delete_environment_async(uuid.UUID(env_id), uuid.UUID(tenant_id))
        except Exception as exc:
            logger.warning("delete_dev_environment_error", env_id=env_id, error=str(exc))
            return {"env_id": env_id, "status": "error", "error": str(exc)}

    # 通知前端列表/详情缓存失效 (记录已删除, status_changed 事件无意义)
    await publish_ws_event(
        tenant_id=uuid.UUID(tenant_id),
        event="dev_environment.deleted",
        payload={"id": env_id},
    )
    return {"env_id": env_id, "status": "deleted"}


@broker.task(
    task_name="app.tasks.dev_environment.sync_statuses",
    schedule=[{"cron": interval_to_cron(settings.DEV_ENV_STATUS_SYNC_INTERVAL_SECONDS)}],
)
async def sync_dev_environment_statuses_task(limit: int = 200) -> dict[str, Any]:
    """定时同步非终态开发环境的 JupyterHub 状态."""
    async with async_session_factory() as db:
        svc = DevEnvironmentService(db)
        synced_count = await svc.sync_non_terminal_environments(limit=limit)

    return {"synced_count": synced_count}


@broker.task(
    task_name="app.tasks.dev_environment.check_idle",
    schedule=[{"cron": interval_to_cron(settings.DEV_ENV_IDLE_CHECK_INTERVAL_SECONDS)}],
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


async def enqueue_dev_environment_start(env_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """将开发环境启动任务入队 (从 API endpoint 调用)."""
    await start_dev_environment_task.kiq(str(env_id), str(tenant_id))


async def enqueue_dev_environment_stop(
    env_id: uuid.UUID,
    tenant_id: uuid.UUID,
    stopped_reason: str = "manual",
) -> None:
    """将开发环境停止任务入队 (从 API endpoint 调用)."""
    await stop_dev_environment_task.kiq(str(env_id), str(tenant_id), stopped_reason)


async def enqueue_dev_environment_delete(env_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    """将开发环境删除任务入队 (从 API endpoint 调用)."""
    await delete_dev_environment_task.kiq(str(env_id), str(tenant_id))
