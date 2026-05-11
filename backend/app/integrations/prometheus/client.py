from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.core.config import settings

logger = structlog.get_logger()


class PrometheusClient:
    """Async Prometheus HTTP API client for querying DCGM GPU metrics."""

    def __init__(self, base_url: str | None = None) -> None:
        self._base_url = (base_url or settings.PROMETHEUS_URL).rstrip("/")
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(30.0, connect=5.0),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def instant_query(self, query: str) -> dict[str, Any]:
        """GET /api/v1/query — instant query returning current values."""
        client = await self._get_client()
        resp = await client.get("/api/v1/query", params={"query": query})
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {data.get('error')}")
        result: dict[str, Any] = data["data"]
        return result

    async def range_query(self, query: str, start: str, end: str, step: str = "15s") -> dict[str, Any]:
        """GET /api/v1/query_range — range query returning time series data."""
        client = await self._get_client()
        resp = await client.get(
            "/api/v1/query_range",
            params={"query": query, "start": start, "end": end, "step": step},
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        if data.get("status") != "success":
            raise RuntimeError(f"Prometheus query failed: {data.get('error')}")
        result: dict[str, Any] = data["data"]
        return result

    async def query_gpu_metrics(self, namespace: str, pod_name: str | None = None) -> list[dict[str, Any]]:
        """Query instant GPU metrics for a namespace (optionally filtered by pod)."""
        label_filter = f'namespace="{namespace}"'
        if pod_name:
            label_filter += f',pod="{pod_name}"'

        query = (
            '{__name__=~"DCGM_FI_DEV_GPU_UTIL|DCGM_FI_DEV_FB_USED'
            '|DCGM_FI_DEV_FB_FREE|DCGM_FI_DEV_GPU_TEMP|DCGM_FI_DEV_POWER_USAGE",'
            f"{label_filter}}}"
        )
        data = await self.instant_query(query)
        results: list[dict[str, Any]] = data.get("result", [])
        return results

    async def query_gpu_utilization_range(
        self,
        namespace: str,
        pod_name: str | None,
        start: str,
        end: str,
        step: str = "15s",
    ) -> list[dict[str, Any]]:
        """Query GPU utilization history as time series."""
        label_filter = f'namespace="{namespace}"'
        if pod_name:
            label_filter += f',pod="{pod_name}"'

        query = f"avg by (pod, gpu) (DCGM_FI_DEV_GPU_UTIL{{{label_filter}}})"
        data = await self.range_query(query, start, end, step)
        results: list[dict[str, Any]] = data.get("result", [])
        return results
