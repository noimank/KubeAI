from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory
from app.integrations.k8s.namespace import list_tenant_namespaces
from app.integrations.volcano.client import (
    delete_vcjob,
    extract_vcjob_phase,
    list_vcjobs,
)
from app.models.enums import AuditAction, ResourceType, TrainingJobStatus
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.services.audit_service import AuditService

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

TERMINAL_STATUSES = {TrainingJobStatus.SUCCEEDED, TrainingJobStatus.FAILED, TrainingJobStatus.STOPPED}


@dataclass
class StaleJobInfo:
    id: uuid.UUID
    name: str
    tenant_name: str
    namespace: str
    vcjob_name: str
    status: str
    finished_at: datetime | None
    days_ago: int


class ResourceCleaner:
    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._semaphore = asyncio.Semaphore(3)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._clean_loop())
            logger.info("resource_cleaner_started")

    async def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            logger.info("resource_cleaner_stopped")

    async def _clean_loop(self) -> None:
        while True:
            try:
                await asyncio.sleep(settings.RESOURCE_CLEANUP_INTERVAL_SECONDS)
                await self._run_cleanup()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("resource_cleanup_error")
                await asyncio.sleep(60)

    async def _run_cleanup(self) -> None:
        namespaces = await list_tenant_namespaces()
        cleaned_jobs = 0
        scanned_namespaces = len(namespaces)

        async with async_session_factory() as db:
            for namespace in namespaces:
                async with self._semaphore:
                    try:
                        cleaned = await self._cleanup_namespace_jobs(db, namespace)
                        cleaned_jobs += cleaned
                    except Exception:
                        logger.exception("cleanup_namespace_failed", namespace=namespace)

            if cleaned_jobs > 0:
                await db.commit()

        logger.info(
            "resource_cleanup_completed",
            cleaned_jobs=cleaned_jobs,
            scanned_namespaces=scanned_namespaces,
        )

    async def _cleanup_namespace_jobs(self, db: AsyncSession, namespace: str) -> int:

        vcjobs = await list_vcjobs(namespace)
        vcjob_map: dict[str, dict[str, object]] = {v.get("metadata", {}).get("name", ""): v for v in vcjobs}

        # Find tenant for audit logging
        tenant_result = await db.execute(select(Tenant).where(Tenant.k8s_namespace_name == namespace))
        tenant = tenant_result.scalar_one_or_none()

        threshold = datetime.now(UTC) - timedelta(days=settings.RESOURCE_CLEANUP_JOB_MAX_AGE_DAYS)

        if not tenant:
            return 0

        stmt = select(TrainingJob).where(
            TrainingJob.tenant_id == tenant.id,
            TrainingJob.status.in_([s.value for s in TERMINAL_STATUSES]),
        )
        result = await db.execute(stmt)
        terminal_jobs = list(result.scalars().all())

        cleaned = 0
        audit_svc = AuditService(db)

        for job in terminal_jobs:
            if not job.finished_at:
                continue
            finished_at = job.finished_at
            if finished_at.tzinfo is None:
                finished_at = finished_at.replace(tzinfo=UTC)
            if finished_at >= threshold:
                continue

            vcjob_name = job.vcjob_name
            if not vcjob_name:
                continue

            vcjob = vcjob_map.get(vcjob_name)
            if vcjob:
                phase = extract_vcjob_phase(vcjob)
                if phase not in (TrainingJobStatus.SUCCEEDED.value, TrainingJobStatus.FAILED.value):
                    continue
                await delete_vcjob(namespace, vcjob_name)
            # If VCJob doesn't exist in K8s, nothing to delete

            days_ago = (datetime.now(UTC) - finished_at).days
            await audit_svc.log_action(
                action=AuditAction.CLEANUP_JOB,
                resource_type=ResourceType.TRAINING_JOB,
                resource_id=str(job.id),
                tenant_id=tenant.id,
                ip_address="",
                detail={
                    "tenant_id": str(tenant.id),
                    "tenant_name": tenant.display_name or tenant.name,
                    "vcjob_name": vcjob_name,
                    "job_id": str(job.id),
                    "job_name": job.name,
                    "completed_days_ago": days_ago,
                    "source": "auto_cleanup",
                },
            )
            cleaned += 1

        return cleaned

    async def detect_stale_jobs(self) -> list[StaleJobInfo]:
        async with async_session_factory() as db:
            threshold = datetime.now(UTC) - timedelta(days=settings.RESOURCE_CLEANUP_JOB_MAX_AGE_DAYS)
            stmt = (
                select(TrainingJob, Tenant)
                .join(Tenant, TrainingJob.tenant_id == Tenant.id)
                .where(
                    TrainingJob.status.in_([s.value for s in TERMINAL_STATUSES]),
                    TrainingJob.finished_at < threshold,
                )
            )
            result = await db.execute(stmt)
            rows = list(result.all())

            stale_jobs: list[StaleJobInfo] = []
            for job, tenant in rows:
                finished_at = job.finished_at
                if finished_at and finished_at.tzinfo is None:
                    finished_at = finished_at.replace(tzinfo=UTC)
                days_ago = (datetime.now(UTC) - finished_at).days if finished_at else 0
                stale_jobs.append(
                    StaleJobInfo(
                        id=job.id,
                        name=job.name,
                        tenant_name=tenant.display_name or tenant.name,
                        namespace=tenant.k8s_namespace_name or "",
                        vcjob_name=job.vcjob_name or "",
                        status=job.status,
                        finished_at=job.finished_at,
                        days_ago=days_ago,
                    )
                )
            return stale_jobs

    async def trigger_manual_cleanup(self) -> None:
        self._manual_task: asyncio.Task[None] | None = asyncio.create_task(self._run_cleanup())
