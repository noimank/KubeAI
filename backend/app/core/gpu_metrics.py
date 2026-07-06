"""Shared GPU metric parsing utilities and response model.

Used by both inference service and training job endpoints to avoid duplicated
Prometheus result parsing logic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class GpuMetricPoint(BaseModel):
    """单张 GPU 的瞬时指标快照."""

    gpu_index: int
    utilization_percent: float
    memory_used_mib: float
    memory_total_mib: float
    temperature_c: float
    power_w: float


class TimeSeriesPoint(BaseModel):
    """时序数据点."""

    timestamp: str
    value: float
    label: str


class MetricsResponse(BaseModel):
    """GPU 监控指标响应 (推理服务 & 训练任务共用)."""

    gpu_metrics: list[GpuMetricPoint]
    gpu_utilization_history: list[TimeSeriesPoint]
    metrics_url: str | None
    prometheus_available: bool
    timestamp: str


# ---------------------------------------------------------------------------
# Parsing functions
# ---------------------------------------------------------------------------

DCGM_GPU_UTIL = "DCGM_FI_DEV_GPU_UTIL"
DCGM_FB_USED = "DCGM_FI_DEV_FB_USED"
DCGM_FB_FREE = "DCGM_FI_DEV_FB_FREE"
DCGM_GPU_TEMP = "DCGM_FI_DEV_GPU_TEMP"
DCGM_POWER_USAGE = "DCGM_FI_DEV_POWER_USAGE"


def parse_gpu_metrics(raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse Prometheus instant query results into GPU metric dicts."""
    gpu_data: dict[int, dict[str, float]] = {}
    for item in raw_results:
        metric = item.get("metric", {})
        gpu_idx = int(metric.get("gpu", "0"))
        name = metric.get("__name__", "")
        value = float(item.get("value", [0, "0"])[1])

        if gpu_idx not in gpu_data:
            gpu_data[gpu_idx] = {}
        gpu_data[gpu_idx][name] = value

    points: list[dict[str, Any]] = []
    for idx in sorted(gpu_data.keys()):
        d = gpu_data[idx]
        fb_used = d.get(DCGM_FB_USED, 0)
        fb_free = d.get(DCGM_FB_FREE, 0)
        points.append(
            {
                "gpu_index": idx,
                "utilization_percent": d.get(DCGM_GPU_UTIL, 0),
                "memory_used_mib": fb_used,
                "memory_total_mib": fb_used + fb_free,
                "temperature_c": d.get(DCGM_GPU_TEMP, 0),
                "power_w": d.get(DCGM_POWER_USAGE, 0),
            }
        )
    return points


def parse_gpu_history(raw_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse Prometheus range query results into time series dicts."""
    points: list[dict[str, Any]] = []
    for series in raw_results:
        metric = series.get("metric", {})
        label = f"GPU {metric.get('gpu', '?')}"
        for ts, val in series.get("values", []):
            dt = datetime.fromtimestamp(float(ts), tz=UTC)
            points.append(
                {
                    "timestamp": dt.isoformat(),
                    "value": float(val),
                    "label": label,
                }
            )
    return points


def parse_duration(duration: str) -> timedelta:
    """Parse duration string (e.g. '20m', '1h', '30s') into timedelta.

    Returns timedelta(minutes=20) on invalid input.
    """
    try:
        unit = duration[-1]
        value = int(duration[:-1])
    except (IndexError, ValueError):
        return timedelta(minutes=20)
    if unit == "s":
        return timedelta(seconds=value)
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    return timedelta(minutes=20)


# ---------------------------------------------------------------------------
# Convenience helpers for building degraded / success responses
# ---------------------------------------------------------------------------


def degraded_response(metrics_url: str | None = None) -> dict[str, Any]:
    """Return a degraded response when Prometheus is unavailable."""
    return {
        "gpu_metrics": [],
        "gpu_utilization_history": [],
        "metrics_url": metrics_url,
        "prometheus_available": False,
        "timestamp": datetime.now(UTC).isoformat(),
    }


def metrics_success(
    gpu_metrics: list[dict[str, Any]],
    history: list[dict[str, Any]],
    metrics_url: str | None = None,
) -> dict[str, Any]:
    """Build successful metrics response dict."""
    return {
        "gpu_metrics": gpu_metrics,
        "gpu_utilization_history": history,
        "metrics_url": metrics_url,
        "prometheus_available": True,
        "timestamp": datetime.now(UTC).isoformat(),
    }
