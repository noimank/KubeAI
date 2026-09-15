"""Shared integration-client singletons — safe for FastAPI lifespan, Taskiq workers, and any
other process entry-point.

Usage::

    from app.core.clients import get_harbor_client

    client = get_harbor_client()   # created on first access, cached thereafter

    # At process shutdown:
    await close_clients()

Integrity: every ``get_xxx_client()`` returns a process-local cached instance.  Calling
``init_clients()`` early (e.g. in FastAPI lifespan / Taskiq startup) warms up all clients
and surfaces configuration errors early.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from app.core.config import settings
from app.integrations.casdoor.client import CasdoorClient
from app.integrations.harbor.client import HarborClient
from app.integrations.minio import MinIOClient
from app.integrations.prometheus.client import PrometheusClient

if TYPE_CHECKING:
    from app.integrations.mlflow.client import MLflowClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Per-client lazy singletons
# ---------------------------------------------------------------------------

_harbor_client: HarborClient | None = None
_minio_client: MinIOClient | None = None
_prometheus_client: PrometheusClient | None = None
_mlflow_client: MLflowClient | None = None
_casdoor_client: CasdoorClient | None = None


def get_harbor_client() -> HarborClient:
    global _harbor_client
    if _harbor_client is None:
        _harbor_client = HarborClient()
    return _harbor_client


def get_minio_client() -> MinIOClient:
    global _minio_client
    if _minio_client is None:
        _minio_client = MinIOClient()
    return _minio_client


def get_prometheus_client() -> PrometheusClient | None:
    global _prometheus_client
    if _prometheus_client is None and settings.PROMETHEUS_URL:
        _prometheus_client = PrometheusClient()
    return _prometheus_client


def get_mlflow_client() -> MLflowClient:
    global _mlflow_client
    if _mlflow_client is None:
        from app.integrations.mlflow.client import MLflowClient

        _mlflow_client = MLflowClient()
    return _mlflow_client


def get_casdoor_client() -> CasdoorClient:
    global _casdoor_client
    if _casdoor_client is None:
        if not settings.OIDC_ISSUER:
            raise RuntimeError("Casdoor 客户端未初始化: 未配置 OIDC_ISSUER")
        _casdoor_client = CasdoorClient()
    return _casdoor_client


async def _check_mlflow_health() -> bool:
    """Verify MLflow tracking server is reachable at startup.

    Returns False (and warns) when unreachable rather than raising — MLflow is a
    per-job opt-in integration, so a transient MLflow outage must not block the
    whole backend from starting (e.g. during a rollout). Jobs that opt into MLflow
    will fail individually at experiment-creation time instead.
    """
    import httpx

    from app.core.config import settings

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.MLFLOW_TRACKING_URI.rstrip('/')}/health")
            resp.raise_for_status()
        return True
    except Exception as exc:
        logger.warning(
            "MLflow tracking server unreachable at %s: %s. MLflow-dependent training jobs "
            "will fail until it recovers; other platform functionality is unaffected.",
            settings.MLFLOW_TRACKING_URI,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# Bulk lifecycle
# ---------------------------------------------------------------------------


async def init_clients() -> None:
    """Warm up all integration clients.  Idempotent — safe to call more than once."""
    from app.core.redis import init_redis

    await init_redis()
    get_harbor_client()
    get_minio_client()
    get_prometheus_client()  # may be None if PROMETHEUS_URL not set

    get_mlflow_client()
    if settings.OIDC_ISSUER:
        get_casdoor_client()
    await _check_mlflow_health()

    logger.info("clients_initialized")


async def close_clients() -> None:
    """Close all integration clients.  Idempotent — safe to call more than once."""
    global _harbor_client, _minio_client, _prometheus_client
    global _mlflow_client, _casdoor_client

    if _harbor_client is not None:
        await _harbor_client.close()
        _harbor_client = None
    if _minio_client is not None:
        _minio_client.close()
        _minio_client = None
    if _prometheus_client is not None:
        await _prometheus_client.close()
        _prometheus_client = None
    if _mlflow_client is not None:
        await _mlflow_client.close()
        _mlflow_client = None
    if _casdoor_client is not None:
        await _casdoor_client.close()
        _casdoor_client = None

    from app.core.redis import close_redis
    from app.integrations.k8s.client import close_k8s_clients

    await close_k8s_clients()
    await close_redis()

    logger.info("clients_closed")
