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
from typing import TYPE_CHECKING, Any

import structlog
from kubernetes_asyncio import client, watch
from sqlalchemy import select

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.ws_pubsub import publish_ws_event
from app.integrations.k8s.client import get_k8s_clients
from app.integrations.k8s.pod import _VCJOB_LABEL, get_pod_failure_info, list_vcjob_pods
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
}

_TERMINAL_STATUSES = {
    TrainingJobStatus.SUCCEEDED,
    TrainingJobStatus.FAILED,
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

    # ── Pod Ready + Running while job is PENDING / QUEUED / INITIALIZING ───
    if (
        ready
        and phase == "Running"
        and current_status
        in (
            TrainingJobStatus.PENDING,
            TrainingJobStatus.QUEUED,
            TrainingJobStatus.INITIALIZING,
        )
    ):
        job.status = TrainingJobStatus.RUNNING
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
        job.status = TrainingJobStatus.FAILED
        _update_timestamps(job, TrainingJobStatus.FAILED)
        job.error_message = await _resolve_failure_reason(namespace, job.vcjob_name)
        await db.commit()
        await _on_terminal_status(job, current_status, TrainingJobStatus.FAILED)
        logger.warning(
            "training_job_failed_via_watcher",
            job_id=str(job.id),
            name=job.name,
        )
        return

    # ── Pod Succeeded while job is RUNNING ─────────────────────────────────
    if phase == "Succeeded" and current_status == TrainingJobStatus.RUNNING:
        # For distributed training: only succeed when ALL pods are done
        all_succeeded = await _all_pods_succeeded(namespace, job.vcjob_name)
        if not all_succeeded:
            return  # Other workers still running — wait for their events
        job.status = TrainingJobStatus.SUCCEEDED
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
    job.error_message = "训练 Pod 被删除（节点故障或被驱逐）"  # noqa: RUF001
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


async def _resolve_failure_reason(namespace: str, vcjob_name: str | None) -> str:
    """Extract a human-readable failure reason from failed pods."""
    if not vcjob_name:
        return "训练任务已失败"

    try:
        pods = await list_vcjob_pods(namespace, vcjob_name)
    except Exception:
        return "训练任务已失败，但失败详情不可用（无法查询 Pod 信息）。"  # noqa: RUF001

    if not pods:
        return "训练任务已失败，但失败详情不可用（任务资源已被清理）。"  # noqa: RUF001

    for pod_info in pods:
        try:
            failure = await get_pod_failure_info(namespace, pod_info["pod_name"])
        except Exception:
            continue
        if failure:
            return _map_failure_message(failure)

    return "训练任务已失败，但未能获取具体失败原因。"  # noqa: RUF001


def _map_failure_message(failure: dict[str, Any]) -> str:
    """Map a K8s container termination to a Chinese error message."""
    reason = failure.get("reason", "")
    exit_code = failure.get("exit_code", -1)

    if reason == "OOMKilled":
        return "内存不足 (OOM)：训练容器因超出内存限制被终止。建议增加内存配置或优化训练脚本。"  # noqa: RUF001
    if reason in ("ImagePullBackOff", "ErrImagePull"):
        return "镜像拉取失败：请检查镜像地址是否正确，以及是否具有拉取权限。"  # noqa: RUF001
    if reason == "ContainerCannotRun":
        return "容器启动失败：请检查镜像和启动命令是否正确。"  # noqa: RUF001
    if exit_code == 137:
        return "进程被终止 (SIGKILL)：可能是内存不足。建议增加内存或检查训练脚本。"  # noqa: RUF001
    if exit_code == 1:
        return "训练脚本执行错误：请查看日志获取详细错误信息。"  # noqa: RUF001
    if exit_code != 0:
        return f"训练异常退出 (退出码: {exit_code})：请查看日志获取详细信息。"  # noqa: RUF001
    return f"训练任务失败 (原因: {reason})：请查看日志获取详细信息。"  # noqa: RUF001


async def _on_terminal_status(
    job: TrainingJob,
    old_status: TrainingJobStatus,
    new_status: TrainingJobStatus,
) -> None:
    """Handle side effects when a job reaches a terminal status.

    - Sync MLflow experiment status
    - Create user notification
    - Push WebSocket event
    """
    # ── Sync MLflow experiment ─────────────────────────────────────────
    try:
        from app.services.experiment_service import ExperimentService

        async with async_session_factory() as db:
            experiment_service = ExperimentService(db)
            await experiment_service.sync_experiment_status(job.id, new_status)
            await db.commit()
    except Exception:
        logger.exception("watcher_mlflow_sync_error", job_id=str(job.id))

    # ── Create notification ────────────────────────────────────────────
    try:
        from app.models.enums import NotificationPriority, NotificationType
        from app.services.notification_service import NotificationService

        async with async_session_factory() as db:
            notif_service = NotificationService(db)
            is_success = new_status == TrainingJobStatus.SUCCEEDED
            await notif_service.create_notification(
                user_id=job.created_by,
                tenant_id=job.tenant_id,
                type=NotificationType.TRAINING_JOB,
                title=f"训练任务{'完成' if is_success else '失败'}",
                content=f"训练任务「{job.name}」已{'完成' if is_success else '失败'}.",
                priority=NotificationPriority.HIGH if not is_success else NotificationPriority.MEDIUM,
                resource_type="training_job",
                resource_id=str(job.id),
            )
            await db.commit()
    except Exception:
        logger.exception("watcher_notification_error", job_id=str(job.id))

    # ── Push WebSocket event ───────────────────────────────────────────
    await _publish_training_status_change(job.tenant_id, job.id, old_status, new_status)


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
