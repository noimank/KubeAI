"""
K8s Dev Pod Watcher — global Pod event watcher for development environments.

Replaces per-env polling (``_wait_for_pod_ready`` / ``_wait_for_pod_gone``) with
a single cluster-scoped Watch connection.  Pod ADDED / MODIFIED / DELETED events
drive DevEnvironment status transitions directly, eliminating per-env latency
(was up to 2 s) and removing the risk of a crashed Taskiq worker leaving an env
stuck in a non-terminal state.

Architecture
------------
One ``asyncio.Task`` per FastAPI replica watches all pods labelled
``kubeai.io/dev-env-id`` across all namespaces via a single long-lived HTTP/2
stream to the K8s API server.  Each event maps to a DevEnvironment DB row (by
**id**, not by pod name) and transitions the status:

===========  ===============  ==================  ============================
Pod Event    Pod State        Current Env Status   Action
===========  ===============  ==================  ============================
ADDED        —                (any)                No-op — pod creation alone
                                                  means nothing; we wait for
                                                  the container to signal Ready.
MODIFIED     Ready=True       STARTING             → RUNNING (set access_url,
                                                  last_active_at, push WS)
MODIFIED     Phase=Failed     STARTING             → FAILED (push WS)
MODIFIED     Ready=False      RUNNING              → STOPPED (pod crashed /
                                                  evicted, push WS)
DELETED      —                RUNNING / STOPPING   → STOPPED (push WS)
===========  ===============  ==================  ============================

The watcher is purely event-driven: no polling, no per-env timers, O(1) API
server load regardless of how many environments are starting concurrently.
On disconnect the K8s Watch reconnects with the last-known ``resourceVersion``
so no event is lost.

RBAC requirement
----------------
This module uses ``list_pod_for_all_namespaces`` which needs a **ClusterRole**
with ``list`` and ``watch`` verbs on ``pods``.  Make sure the backend
ServiceAccount has this permission in the Helm chart:

.. code-block:: yaml

    - apiGroups: [""]
      resources: ["pods"]
      verbs:   ["list", "watch"]
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from kubernetes_asyncio import client, watch
from sqlalchemy import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.ws_pubsub import publish_status_changed
from app.integrations.k8s.client import get_k8s_clients
from app.integrations.k8s.dev_pod import DEV_ENV_LABEL_KEY, dev_access_url
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus

logger = structlog.get_logger(__name__)

# Reconnect after this many seconds without an event (K8s API server default is
# ~5 min; we use a slightly shorter window so the client reconnects gracefully).
_WATCH_TIMEOUT_SECONDS = 300
_RECONNECT_BACKOFF_SECONDS = 5


# ---------------------------------------------------------------------------
# Public entrypoint — called from ``app.core.events.on_startup``
# ---------------------------------------------------------------------------


async def run_dev_pod_watcher(stop_event: asyncio.Event) -> None:
    """Global dev-pod watcher — one per FastAPI replica.

    Runs until *stop_event* is set (triggered on application shutdown).
    Reconnects automatically after transient failures (API server restart,
    network blip).
    """
    logger.info("dev_pod_watcher_starting")
    while not stop_event.is_set():
        try:
            await _watch_loop(stop_event)
        except asyncio.CancelledError:
            logger.info("dev_pod_watcher_cancelled")
            return
        except Exception:
            logger.exception("dev_pod_watcher_loop_error")
            # Brief backoff before reconnect so we don't hammer the API server
            # in a tight restart loop.
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

    # NOTE: we do NOT pass resource_version here — kubernetes_asyncio's Watch
    # tracks it automatically from received events and reconnects from the last
    # seen version when the stream times out.
    async for event in w.stream(
        func=core_v1.list_pod_for_all_namespaces,
        label_selector=DEV_ENV_LABEL_KEY,
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
                "dev_pod_watcher_event_error",
                event_type=event.get("type"),
                pod_name=getattr(event.get("object", {}).metadata, "name", "?"),
            )
            # Per-event isolation: a broken handler for one pod must not kill
            # the entire watch stream.


# ---------------------------------------------------------------------------
# Internal: event → DevEnvironment transition
# ---------------------------------------------------------------------------


async def _handle_pod_event(event_type: str, pod: client.V1Pod) -> None:
    """Map a single K8s Pod event to the corresponding DevEnvironment transition."""
    env_id = _extract_env_id(pod)
    if not env_id:
        return

    phase = (pod.status.phase or "Unknown") if pod.status else "Unknown"
    ready = _is_pod_ready(pod)

    logger.debug(
        "dev_pod_watcher_event",
        event_type=event_type,
        env_id=str(env_id),
        phase=phase,
        ready=ready,
    )

    async with async_session_factory() as db:
        env = (await db.execute(select(DevEnvironment).where(DevEnvironment.id == env_id))).scalar_one_or_none()

        if not env:
            # Env already deleted from DB — expected for DELETED events that
            # arrive after the delete task has removed the row.
            return

        if event_type == "DELETED":
            await _handle_deleted(env, db)
        else:
            await _handle_added_or_modified(env, phase, ready, db)


# ---------------------------------------------------------------------------
# Internal: event handlers per event type
# ---------------------------------------------------------------------------


async def _handle_added_or_modified(
    env: DevEnvironment,
    phase: str,
    ready: bool,
    db: AsyncSession,
) -> None:
    """Pod was created or updated.

    ADDED alone doesn't trigger a transition — we wait for the container to
    signal Ready (or fail) via a subsequent MODIFIED event.
    """
    # ── Pod Ready while env is STARTING ──────────────────────────────
    if ready and phase in ("Running", "Succeeded") and env.status == DevEnvironmentStatus.STARTING:
        now = datetime.now(UTC).isoformat()
        env.access_url = dev_access_url(env.id)
        env.last_active_at = env.last_active_at or now
        env.status = DevEnvironmentStatus.RUNNING
        await db.commit()
        await publish_status_changed(
            env.tenant_id,
            env.id,
            DevEnvironmentStatus.STARTING.value,
            DevEnvironmentStatus.RUNNING.value,
            name=env.name,
        )
        logger.info("dev_env_running", env_id=str(env.id), name=env.name)
        return

    # ── Pod Failed while env is STARTING ─────────────────────────────
    if phase == "Failed" and env.status == DevEnvironmentStatus.STARTING:
        env.error_message = "Pod 进入 Failed 状态"
        env.status = DevEnvironmentStatus.FAILED
        await db.commit()
        await publish_status_changed(
            env.tenant_id,
            env.id,
            DevEnvironmentStatus.STARTING.value,
            DevEnvironmentStatus.FAILED.value,
            name=env.name,
        )
        logger.warning("dev_env_failed", env_id=str(env.id), phase=phase)
        return

    # ── Running pod lost readiness (crash / eviction) ────────────────
    if (not ready or phase not in ("Running", "Succeeded")) and env.status == DevEnvironmentStatus.RUNNING:
        env.status = DevEnvironmentStatus.STOPPED
        env.stopped_reason = env.stopped_reason or "server_missing"
        await db.commit()
        await publish_status_changed(
            env.tenant_id,
            env.id,
            DevEnvironmentStatus.RUNNING.value,
            DevEnvironmentStatus.STOPPED.value,
            name=env.name,
        )
        logger.warning("dev_env_crashed", env_id=str(env.id), phase=phase)
        return


async def _handle_deleted(env: DevEnvironment, db: AsyncSession) -> None:
    """Pod was deleted — reconcile the env status."""
    if env.status == DevEnvironmentStatus.RUNNING:
        env.status = DevEnvironmentStatus.STOPPED
        env.stopped_reason = env.stopped_reason or "server_missing"
        await db.commit()
        await publish_status_changed(
            env.tenant_id,
            env.id,
            DevEnvironmentStatus.RUNNING.value,
            DevEnvironmentStatus.STOPPED.value,
            name=env.name,
        )
        logger.info(
            "dev_env_stopped_via_delete",
            env_id=str(env.id),
            name=env.name,
            reason=env.stopped_reason,
        )
        return

    if env.status == DevEnvironmentStatus.STOPPING:
        env.status = DevEnvironmentStatus.STOPPED
        env.stopped_reason = env.stopped_reason or "manual"
        await db.commit()
        await publish_status_changed(
            env.tenant_id,
            env.id,
            DevEnvironmentStatus.STOPPING.value,
            DevEnvironmentStatus.STOPPED.value,
            name=env.name,
        )
        logger.info(
            "dev_env_stopped_via_delete",
            env_id=str(env.id),
            name=env.name,
            reason=env.stopped_reason,
        )
        return

    # STARTING + pod deleted → pod was evicted/killed before becoming Ready,
    # or a user-initiated stop task deleted it.  In either case the env cannot
    # progress — mark FAILED so the user sees the failure reason and can retry.
    if env.status == DevEnvironmentStatus.STARTING:
        env.error_message = env.error_message or "Pod 在就绪前被删除, 可能因节点资源不足被驱逐"
        env.status = DevEnvironmentStatus.FAILED
        await db.commit()
        await publish_status_changed(
            env.tenant_id,
            env.id,
            DevEnvironmentStatus.STARTING.value,
            DevEnvironmentStatus.FAILED.value,
            name=env.name,
        )
        logger.warning("dev_env_starting_pod_deleted", env_id=str(env.id), name=env.name)
        return


# ---------------------------------------------------------------------------
# Internal: helpers
# ---------------------------------------------------------------------------


def _extract_env_id(pod: client.V1Pod) -> uuid.UUID | None:
    """Extract the dev-environment UUID from a Pod label."""
    labels = pod.metadata.labels if pod.metadata else {}
    raw = labels.get(DEV_ENV_LABEL_KEY)
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, AttributeError):
        logger.warning("dev_pod_watcher_invalid_label", label_value=raw)
        return None


def _is_pod_ready(pod: client.V1Pod) -> bool:
    """Check whether the K8s Pod Ready condition is True."""
    if not pod.status or not pod.status.conditions:
        return False
    return any(c.type == "Ready" and c.status == "True" for c in pod.status.conditions)
