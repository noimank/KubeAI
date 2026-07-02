from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from taskiq import TaskiqEvents, TaskiqScheduler
from taskiq.schedule_sources import LabelScheduleSource
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

from app.core.config import settings


def _redis_url(db: int) -> str:
    parsed = urlsplit(settings.REDIS_URL)
    return urlunsplit((parsed.scheme, parsed.netloc, f"/{db}", parsed.query, parsed.fragment))


def interval_to_cron(seconds: int) -> str:
    """Convert interval in seconds to a cron expression for LabelScheduleSource."""
    minutes = max(1, seconds // 60)
    if minutes == 1:
        return "* * * * *"
    if minutes < 60:
        return f"*/{minutes} * * * *"
    hours = minutes // 60
    return f"0 */{hours} * * *"


broker_url = _redis_url(settings.TASKIQ_BROKER_DB)
result_backend_url = _redis_url(settings.TASKIQ_RESULT_BACKEND_DB)

result_backend: RedisAsyncResultBackend[Any] = RedisAsyncResultBackend(
    redis_url=result_backend_url,
    result_ex_time=3600,  # Task results expire after 1 hour
)

broker = RedisStreamBroker(url=broker_url).with_result_backend(result_backend)

scheduler = TaskiqScheduler(
    broker=broker,
    sources=[LabelScheduleSource(broker)],
)


# ── Shared client lifecycle (same as FastAPI on_startup / on_shutdown) ──────
@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _on_worker_startup(_broker: object) -> None:
    from app.core.clients import init_clients

    await init_clients()


@broker.on_event(TaskiqEvents.WORKER_SHUTDOWN)
async def _on_worker_shutdown(_broker: object) -> None:
    from app.core.clients import close_clients

    await close_clients()


# Import task modules so @broker.task decorators are registered
import app.tasks.annotation_tasks  # noqa: E402
import app.tasks.dataset_tasks  # noqa: E402
import app.tasks.dev_environment_tasks  # noqa: E402
import app.tasks.image_tasks  # noqa: E402
import app.tasks.inference_service_tasks  # noqa: E402
import app.tasks.model_registry_tasks  # noqa: E402
import app.tasks.monitoring_tasks  # noqa: E402
import app.tasks.resource_cleanup_tasks  # noqa: E402
import app.tasks.training_job_tasks  # noqa: E402, F401
