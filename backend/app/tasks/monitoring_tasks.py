from __future__ import annotations

import uuid
from typing import Any

import structlog

from app.core.database import async_session_factory
from app.core.taskiq_app import broker
from app.services.monitoring_service import MonitoringService

logger = structlog.get_logger(__name__)


@broker.task(task_name="app.tasks.monitoring.transfer_quota")
async def transfer_quota_task(
    source_tenant_id: str,
    target_tenant_id: str,
    resource_type: str,
    amount: str,
    force: bool = False,
) -> dict[str, Any]:
    """由 Taskiq worker 执行 K8s ResourceQuota 同步."""
    from app.schemas.monitoring import QuotaTransferRequest

    async with async_session_factory() as db:
        svc = MonitoringService(db)
        await svc.execute_quota_transfer(
            QuotaTransferRequest(
                source_tenant_id=uuid.UUID(source_tenant_id),
                target_tenant_id=uuid.UUID(target_tenant_id),
                resource_type=resource_type,  # type: ignore[arg-type]
                amount=amount,
                force=force,
            ),
        )

    return {"status": "transferred"}


async def enqueue_quota_transfer(
    source_tenant_id: uuid.UUID,
    target_tenant_id: uuid.UUID,
    resource_type: str,
    amount: str,
    force: bool = False,
) -> None:
    await transfer_quota_task.kiq(
        str(source_tenant_id),
        str(target_tenant_id),
        resource_type,
        amount,
        force,
    )
