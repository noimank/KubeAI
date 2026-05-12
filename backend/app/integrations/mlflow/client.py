from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# MLflow Tracking REST API client (MLflow v3 compatible).
# v3 note: experiments/search must use GET + query params (POST body ignored).


class MLflowClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        self._base_url = (base_url or settings.MLFLOW_TRACKING_URI).rstrip("/")
        self._timeout = timeout

    async def search_experiments(
        self, *, filter_expr: str | None = None, max_results: int = 100
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"max_results": max_results}
        if filter_expr:
            params["filter"] = filter_expr
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(f"{self._base_url}/api/2.0/mlflow/experiments/search", params=params)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return cast("list[dict[str, Any]]", data.get("experiments", []))
        except Exception as e:
            logger.warning("MLflow search_experiments failed: %s", e)
            return []

    async def search_runs(
        self,
        *,
        experiment_ids: list[str],
        filter_expr: str | None = None,
        max_results: int = 50,
    ) -> list[dict[str, Any]]:
        body: dict[str, Any] = {
            "experiment_ids": experiment_ids,
            "max_results": max_results,
        }
        if filter_expr:
            body["filter"] = filter_expr
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(f"{self._base_url}/api/2.0/mlflow/runs/search", json=body)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return cast("list[dict[str, Any]]", data.get("runs", []))
        except Exception as e:
            logger.warning("MLflow search_runs failed: %s", e)
            return []

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/api/2.0/mlflow/runs/get",
                    params={"run_id": run_id},
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return cast("dict[str, Any] | None", data.get("run"))
        except Exception as e:
            logger.warning("MLflow get_run failed for %s: %s", run_id, e)
            return None

    async def get_metric_history(self, *, run_id: str, metric_key: str) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    f"{self._base_url}/api/2.0/mlflow/metrics/get-history",
                    params={"run_id": run_id, "metric_key": metric_key},
                )
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                return cast("list[dict[str, Any]]", data.get("metrics", []))
        except Exception as e:
            logger.warning("MLflow get_metric_history failed for %s/%s: %s", run_id, metric_key, e)
            return []


def get_mlflow_client() -> MLflowClient | None:
    if not settings.MLFLOW_ENABLED:
        return None
    return MLflowClient()
