"""
K8s Training Pod Watcher — global Pod event watcher for training jobs.

Replaces poll-on-demand status sync (``_sync_job_status``) with a single
cluster-scoped Watch connection.  Pod ADDED / MODIFIED / DELETED events for
Volcano-managed pods drive TrainingJob status transitions directly, eliminating
the risk of stale DB status when no user is viewing the training-jobs page.

Architecture
------------
One ``asyncio.Task`` per FastAPI replica watches all pods labelled
``volcano.sh/job-name`` across all namespaces via a single long-lived HTTP/2
stream to the K8s API server.  Each event maps to a TrainingJob DB row by
**vcjob_name + namespace** and transitions the status:

===========  ===============  ====================  ============================
Pod Event    Pod State        Current DB Status     Action
===========  ===============  ====================  ============================
MODIFIED     Ready + Running  QUEUED / INITIALIZING → RUNNING (set started_at,
                                                    push WS)
MODIFIED     Ready + Running  PENDING               → RUNNING (set started_at,
                                                    push WS)
MODIFIED     Phase=Failed     non-terminal          → FAILED (extract failure
                                                    reason, sync MLflow, push
                                                    notification + WS)
MODIFIED     Phase=Succeeded  RUNNING               → SUCCEEDED (only when ALL
                                                    pods for this VCJob are
                                                    Succeeded; sync MLflow,
                                                    push notification + WS)
DELETED      —                RUNNING               → FAILED (pod crashed /
                                                    evicted, push WS)
===========  ===============  ====================  ============================

The watcher is purely event-driven: no polling, no per-job timers.  On
disconnect the K8s Watch reconnects with the last-known ``resourceVersion``
so no event is lost.

RBAC requirement
----------------
This module uses ``list_pod_for_all_namespaces`` which needs a **ClusterRole**
with ``list`` and ``watch`` verbs on ``pods`` (same permission as
``dev_pod_watcher.py``).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from kubernetes_asyncio import client, watch
from sqlalchemy import select

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.ws_pubsub import publish_ws_event
from app.integrations.k8s.client import get_k8s_clients
from app.integrations.k8s.pod import _VCJOB_LABEL, list_vcjob_pods, resolve_pod_failure_reason
from app.models.enums import TrainingJobStatus
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob

logger = structlog.get_logger(__name__)

# Reconnect after this many seconds without an event (K8s API server default is
# ~5 min; we use a slightly shorter window so the client reconnects gracefully).
_WATCH_TIMEOUT_SECONDS = 300
_RECONNECT_BACKOFF_SECONDS = 5

# Statuses that are considered non-terminal (watcher will act on events for
# jobs in these statuses only).
_ACTIVE_STATUSES = {
    TrainingJobStatus.PENDING,
    TrainingJobStatus.QUEUED,
    TrainingJobStatus.INITIALIZING,
    TrainingJobStatus.RUNNING,
    TrainingJobStatus.FAILED,  # Volcano may have auto-retried — keep watching
}

_TERMINAL_STATUSES = {
    TrainingJobStatus.SUCCEEDED,
    TrainingJobStatus.STOPPED,
}


# ---------------------------------------------------------------------------
# Public entrypoint — called from ``app.core.events.on_startup``
# ---------------------------------------------------------------------------


async def run_training_pod_watcher(stop_event: asyncio.Event) -> None:
    """Global training-pod watcher — one per FastAPI replica.

    Runs until *stop_event* is set (triggered on application shutdown).
    Reconnects automatically after transient failures (API server restart,
    network blip).
    """
    logger.info("training_pod_watcher_starting")
    while not stop_event.is_set():
        try:
            await _watch_loop(stop_event)
        except asyncio.CancelledError:
            logger.info("training_pod_watcher_cancelled")
            return
        except Exception:
            logger.exception("training_pod_watcher_loop_error")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_RECONNECT_BACKOFF_SECONDS)
                return  # stop_event was set during backoff
            except TimeoutError:
                pass  # backoff elapsed, reconnect


# ---------------------------------------------------------------------------
# Internal: watch loop
# ---------------------------------------------------------------------------


async def _watch_loop(stop_event: asyncio.Event) -> None:
    """Open a single Watch stream and process events until timeout or error."""
    k8s = await get_k8s_clients()
    core_v1: client.CoreV1Api = k8s["core_v1"]
    w = watch.Watch()

    async for event in w.stream(
        func=core_v1.list_pod_for_all_namespaces,
        label_selector=_VCJOB_LABEL,
        timeout_seconds=_WATCH_TIMEOUT_SECONDS,
    ):
        if stop_event.is_set():
            return

        try:
            await _handle_pod_event(
                event_type=event["type"],
                pod=event["object"],
            )
        except Exception:
            logger.exception(
                "training_pod_watcher_event_error",
                event_type=event.get("type"),
                pod_name=getattr(event.get("object", {}).metadata, "name", "?"),
            )
            # Per-event isolation: a broken handler for one pod must not kill
            # the entire watch stream.


# ---------------------------------------------------------------------------
# Internal: event → TrainingJob transition
# ---------------------------------------------------------------------------


async def _handle_pod_event(event_type: str, pod: client.V1Pod) -> None:
    """Map a single K8s Pod event to the corresponding TrainingJob transition."""
    vcjob_name = _extract_vcjob_name(pod)
    if not vcjob_name:
        return

    namespace = (pod.metadata.namespace) if pod.metadata else None
    if not namespace:
        return

    phase = (pod.status.phase or "Unknown") if pod.status else "Unknown"
    ready = _is_pod_ready(pod)

    logger.debug(
        "training_pod_watcher_event",
        event_type=event_type,
        vcjob_name=vcjob_name,
        namespace=namespace,
        phase=phase,
        ready=ready,
    )

    async with async_session_factory() as db:
        # Resolve namespace → tenant → TrainingJob
        job = await _find_job_by_vcjob(db, vcjob_name, namespace)
        if not job:
            return  # No DB record (e.g. externally-created VCJob, or already deleted)

        # Only act on non-terminal jobs
        if TrainingJobStatus(job.status) in _TERMINAL_STATUSES:
            return

        if event_type == "DELETED":
            await _handle_deleted(job, db)
        else:
            await _handle_added_or_modified(job, phase, ready, namespace, db)


# ---------------------------------------------------------------------------
# Internal: event handlers per event type
# ---------------------------------------------------------------------------


async def _handle_added_or_modified(
    job: TrainingJob,
    phase: str,
    ready: bool,
    namespace: str,
    db: AsyncSession,
) -> None:
    """Pod was created or updated — reconcile training job status."""
    current_status = TrainingJobStatus(job.status)

    # ── Pod Ready + Running while job is PENDING / QUEUED / INITIALIZING / FAILED ───
    if (
        ready
        and phase == "Running"
        and current_status
        in (
            TrainingJobStatus.PENDING,
            TrainingJobStatus.QUEUED,
            TrainingJobStatus.INITIALIZING,
            TrainingJobStatus.FAILED,
        )
    ):
        job.status = TrainingJobStatus.RUNNING
        job.error_message = None
        _update_timestamps(job, TrainingJobStatus.RUNNING)
        await db.commit()
        await _publish_training_status_change(job.tenant_id, job.id, current_status, TrainingJobStatus.RUNNING)
        logger.info(
            "training_job_running_via_watcher",
            job_id=str(job.id),
            name=job.name,
        )
        return

    # ── Pod Failed while job is active ─────────────────────────────────────
    if phase == "Failed" and current_status in _ACTIVE_STATUSES:
        # Already FAILED: notification was sent on the initial transition;
        # skip duplicate processing from Watch reconnect / repeated events.
        if current_status == TrainingJobStatus.FAILED:
            return
        job.status = TrainingJobStatus.FAILED
        _update_timestamps(job, TrainingJobStatus.FAILED)
        job.error_message = await resolve_pod_failure_reason(namespace, job.vcjob_name)
        await db.commit()
        await _on_terminal_status(job, current_status, TrainingJobStatus.FAILED)
        logger.warning(
            "training_job_failed_via_watcher",
            job_id=str(job.id),
            name=job.name,
        )
        return

    # ── Pod Succeeded while job is RUNNING or FAILED (Volcano may have retried) ───
    if phase == "Succeeded" and current_status in (TrainingJobStatus.RUNNING, TrainingJobStatus.FAILED):
        # For distributed training: only succeed when ALL pods are done
        all_succeeded = await _all_pods_succeeded(namespace, job.vcjob_name)
        if not all_succeeded:
            return  # Other workers still running — wait for their events
        job.status = TrainingJobStatus.SUCCEEDED
        job.error_message = None
        _update_timestamps(job, TrainingJobStatus.SUCCEEDED)
        await db.commit()
        await _on_terminal_status(job, current_status, TrainingJobStatus.SUCCEEDED)
        logger.info(
            "training_job_succeeded_via_watcher",
            job_id=str(job.id),
            name=job.name,
        )
        return


async def _handle_deleted(job: TrainingJob, db: AsyncSession) -> None:
    """Pod was deleted — reconcile the training job status."""
    current_status = TrainingJobStatus(job.status)

    # Already in a terminal state — notification was sent on initial transition.
    if current_status == TrainingJobStatus.FAILED:
        return

    if current_status != TrainingJobStatus.RUNNING:
        # Pod deleted while job is still QUEUED/INITIALIZING — likely evicted
        # or preempted before becoming Ready.
        job.status = TrainingJobStatus.FAILED
        _update_timestamps(job, TrainingJobStatus.FAILED)
        job.error_message = "Pod 在就绪前被删除, 可能因节点资源不足被驱逐"
        await db.commit()
        await _on_terminal_status(job, current_status, TrainingJobStatus.FAILED)
        logger.warning(
            "training_job_pod_deleted_before_ready",
            job_id=str(job.id),
            name=job.name,
            old_status=current_status.value,
        )
        return

    # Pod deleted while RUNNING — crash / eviction / node failure
    job.status = TrainingJobStatus.FAILED
    _update_timestamps(job, TrainingJobStatus.FAILED)
    job.error_message = "训练 Pod 被删除（节点故障或被驱逐）"
    await db.commit()
    await _on_terminal_status(job, current_status, TrainingJobStatus.FAILED)
    logger.warning(
        "training_job_crashed_via_delete",
        job_id=str(job.id),
        name=job.name,
    )


# ---------------------------------------------------------------------------
# Internal: helpers
# ---------------------------------------------------------------------------


def _extract_vcjob_name(pod: client.V1Pod) -> str | None:
    """Extract the Volcano job name from a Pod label."""
    labels = pod.metadata.labels if pod.metadata else {}
    return labels.get(_VCJOB_LABEL)


def _is_pod_ready(pod: client.V1Pod) -> bool:
    """Check whether the K8s Pod Ready condition is True."""
    if not pod.status or not pod.status.conditions:
        return False
    return any(c.type == "Ready" and c.status == "True" for c in pod.status.conditions)


async def _find_job_by_vcjob(
    db: AsyncSession,
    vcjob_name: str,
    namespace: str,
) -> TrainingJob | None:
    """Resolve a VCJob name + namespace to a TrainingJob DB record."""
    # Join Tenant to match namespace, then filter by vcjob_name
    stmt = (
        select(TrainingJob)
        .join(Tenant, TrainingJob.tenant_id == Tenant.id)
        .where(
            TrainingJob.vcjob_name == vcjob_name,
            Tenant.k8s_namespace_name == namespace,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


def _update_timestamps(job: TrainingJob, new_status: TrainingJobStatus) -> None:
    """Update started_at / finished_at based on status transition."""
    if new_status == TrainingJobStatus.RUNNING and not job.started_at:
        job.started_at = datetime.now(UTC)
    elif new_status in _TERMINAL_STATUSES:
        if not job.started_at:
            job.started_at = job.created_at
        if not job.finished_at:
            job.finished_at = datetime.now(UTC)


async def _all_pods_succeeded(namespace: str, vcjob_name: str | None) -> bool:
    """Check whether ALL pods for a VCJob have Succeeded.

    Returns True if no pods exist (edge case: job completed and pods cleaned).
    """
    if not vcjob_name:
        return True
    try:
        pods = await list_vcjob_pods(namespace, vcjob_name)
    except Exception:
        logger.exception("all_pods_succeeded_list_error", vcjob_name=vcjob_name)
        return True  # Err on the side of marking done — fallback sync will correct

    if not pods:
        return True
    return all(p["status"] == "succeeded" for p in pods)


async def _on_terminal_status(
    job: TrainingJob,
    old_status: TrainingJobStatus,
    new_status: TrainingJobStatus,
) -> None:
    """Handle side effects when a job reaches a terminal status.

    - Cleanup TensorBoard Service + APISIX route (if enabled)
    - Sync MLflow experiment status
    - Create user notification
    - Push WebSocket event
    """
    # ── Cleanup TensorBoard resources ───────────────────────────────────
    # TB Service + APISIX route 是手动创建的资源, 没有 TTL.
    # VCJob 自带 ttlSecondsAfterFinished (24h), 但 TB Service 不会随之清理,
    # 必须在此显式删除, 否则会留下指向已终结 Pod 的孤儿 Service.
    if job.tensorboard_enabled and job.vcjob_name:
        try:
            from sqlalchemy import select

            from app.integrations.k8s.tensorboard import get_tensorboard_manager

            async with async_session_factory() as db:
                tenant_row = (await db.execute(select(Tenant).where(Tenant.id == job.tenant_id))).scalar_one_or_none()
                namespace = tenant_row.k8s_namespace_name if tenant_row else None

            if namespace:
                await get_tensorboard_manager().delete(job.id, namespace)
                logger.info(
                    "watcher_tensorboard_cleaned",
                    job_id=str(job.id),
                    namespace=namespace,
                )
            else:
                logger.warning(
                    "watcher_tensorboard_namespace_missing",
                    job_id=str(job.id),
                    tenant_id=str(job.tenant_id),
                )
        except Exception:
            logger.exception("watcher_tensorboard_cleanup_error", job_id=str(job.id))

    # ── Sync MLflow experiment ─────────────────────────────────────────
    try:
        from app.services.experiment_service import ExperimentService

        async with async_session_factory() as db:
            experiment_service = ExperimentService(db)
            await experiment_service.sync_experiment_status(job.id, new_status)
            # FAILED 时主动 KILL run: Pod 被 OOMKilled/强杀时脚本来不及 end_run, 不终止则
            # run 永远停在 RUNNING (停止路径已在 execute_training_job_stop 处理, 此处补 FAILED).
            if new_status == TrainingJobStatus.FAILED:
                await experiment_service.terminate_experiments_for_job(job.id)
            await db.commit()
    except Exception:
        logger.exception("watcher_mlflow_sync_error", job_id=str(job.id))

    # ── Create notification ────────────────────────────────────────────
    try:
        from app.services.notification_service import NotificationService

        async with async_session_factory() as db:
            await NotificationService(db).create_training_outcome_notification(
                job, is_success=(new_status == TrainingJobStatus.SUCCEEDED)
            )
            await db.commit()
    except Exception:
        logger.exception("watcher_notification_error", job_id=str(job.id))

    # ── Push WebSocket event ───────────────────────────────────────────
    await _publish_training_status_change(job.tenant_id, job.id, old_status, new_status)

    # ── Trigger tuning reconcile (trial job 终态 → 立即收尾 + 补发) ──────
    if job.source == "tuning":
        try:
            from app.tasks.tuning_tasks import enqueue_finalize_trial

            await enqueue_finalize_trial(job.id)
        except Exception:
            logger.exception("watcher_tuning_finalize_enqueue_error", job_id=str(job.id))


async def _publish_training_status_change(
    tenant_id: uuid.UUID,
    job_id: uuid.UUID,
    old_status: TrainingJobStatus,
    new_status: TrainingJobStatus,
) -> None:
    """Publish a training job status change via WebSocket."""
    if old_status == new_status:
        return
    await publish_ws_event(
        tenant_id=tenant_id,
        event="training.status_changed",
        payload={
            "id": str(job_id),
            "old_status": old_status.value,
            "new_status": new_status.value,
        },
    )
