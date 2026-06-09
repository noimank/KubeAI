from __future__ import annotations

from typing import Any

import structlog

from app.core.config import settings
from app.core.taskiq_app import broker, interval_to_cron
from app.services.resource_cleaner import cleanup_stale_training_jobs

logger = structlog.get_logger(__name__)


@broker.task(
    task_name="app.tasks.resource_cleanup.run",
    schedule=[{"cron": interval_to_cron(settings.RESOURCE_CLEANUP_INTERVAL_SECONDS)}],
)
async def run_resource_cleanup_task() -> dict[str, Any]:
    """定时清理过期训练任务的 K8s 资源."""
    if not settings.RESOURCE_CLEANUP_ENABLED:
        logger.info("resource_cleanup_skipped", reason="disabled")
        return {"skipped": True, "reason": "disabled"}

    cleaned_jobs, scanned_namespaces = await cleanup_stale_training_jobs()
    return {
        "skipped": False,
        "cleaned_jobs": cleaned_jobs,
        "scanned_namespaces": scanned_namespaces,
    }


async def enqueue_resource_cleanup() -> None:
    """将资源清理任务入队 (从 API endpoint 调用)."""
    await run_resource_cleanup_task.kiq()
