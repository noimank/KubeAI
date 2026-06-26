from __future__ import annotations

import logging
import time
from typing import Any, cast

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# MLflow Tracking REST API client (MLflow v3 compatible).
# v3 note: experiments/search must use GET + query params (POST body ignored).


class MLflowClient:
    def __init__(self, base_url: str | None = None, timeout: float = 10.0) -> None:
        self._base_url = (base_url or settings.MLFLOW_TRACKING_URI).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(timeout),
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def search_experiments(
        self,
        *,
        filter_expr: str | None = None,
        max_results: int = 100,
        view_type: str | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"max_results": max_results}
        if filter_expr:
            params["filter"] = filter_expr
        if view_type:
            params["view_type"] = view_type
        try:
            resp = await self._client.get("/api/2.0/mlflow/experiments/search", params=params)
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
            resp = await self._client.post("/api/2.0/mlflow/runs/search", json=body)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return cast("list[dict[str, Any]]", data.get("runs", []))
        except Exception as e:
            logger.warning("MLflow search_runs failed: %s", e)
            return []

    async def get_run(self, run_id: str) -> dict[str, Any] | None:
        try:
            resp = await self._client.get(
                "/api/2.0/mlflow/runs/get",
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
            resp = await self._client.get(
                "/api/2.0/mlflow/metrics/get-history",
                params={"run_id": run_id, "metric_key": metric_key},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return cast("list[dict[str, Any]]", data.get("metrics", []))
        except Exception as e:
            logger.warning("MLflow get_metric_history failed for %s/%s: %s", run_id, metric_key, e)
            return []

    async def create_experiment(
        self,
        *,
        name: str,
        artifact_location: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> str | None:
        """POST /api/2.0/mlflow/experiments/create.

        Returns the new experiment_id. Returns None on failure.
        Note: if ``name`` already exists the server returns 400 RESOURCE_ALREADY_EXISTS —
        callers should call ``search_experiments`` first or use ``get_or_create_experiment``.
        """
        body: dict[str, Any] = {"name": name}
        if artifact_location:
            body["artifact_location"] = artifact_location
        if tags:
            body["tags"] = [{"key": k, "value": v} for k, v in tags.items()]
        try:
            resp = await self._client.post("/api/2.0/mlflow/experiments/create", json=body)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return cast("str | None", data.get("experiment_id"))
        except Exception as e:
            logger.warning("MLflow create_experiment failed for %s: %s", name, e)
            return None

    async def create_run(
        self,
        *,
        experiment_id: str,
        run_name: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> str | None:
        """POST /api/2.0/mlflow/runs/create — pre-create a run and return its run_id.

        The platform pre-creates a run per training job and injects the run_id into the
        training container as ``MLFLOW_RUN_ID``; the script resumes it via
        ``mlflow.start_run(run_id=...)``. This gives a 1:1 binding between job and run —
        Volcano retries resume the same run instead of spawning new ones. MLflow creates the
        run with ``status=RUNNING``, which is exactly what resume expects.

        Returns the new run_id, or None on failure (caller fail-fasts).
        """
        body: dict[str, Any] = {"experiment_id": experiment_id}
        if run_name:
            body["run_name"] = run_name
        if tags:
            body["tags"] = [{"key": k, "value": v} for k, v in tags.items()]
        try:
            resp = await self._client.post("/api/2.0/mlflow/runs/create", json=body)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            run = cast("dict[str, Any] | None", data.get("run"))
            if not run:
                return None
            return cast("str | None", run.get("info", {}).get("run_id"))
        except Exception as e:
            logger.warning("MLflow create_run failed for experiment %s: %s", experiment_id, e)
            return None

    async def get_or_create_experiment(
        self,
        *,
        name: str,
        artifact_location: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> str | None:
        """Look up an experiment by name, creating it if absent. Returns experiment_id or None.

        Idempotent within MLflow's uniqueness constraint on experiment names — used by the
        platform to ensure a stable experiment_id per TrainingJob across retries. ``tags`` are
        applied only at creation time; an existing *active* experiment keeps its prior tags.

        Handles the soft-delete collision: MLflow reserves the names of deleted experiments, so
        after a training job is deleted and a new job reuses the same name (same tenant + job
        name → same MLflow experiment name), a plain ``create`` returns RESOURCE_ALREADY_EXISTS
        (400). ``create_experiment`` swallows that and returns None; we then search the
        DELETED_ONLY view and, if the name is held by a soft-deleted experiment, restore it and
        reuse the id — rebinding ``tags`` to the new job. This keeps experiment names stable and
        human-readable across delete/recreate cycles instead of leaving the user blocked.
        """
        try:
            experiments = await self.search_experiments(filter_expr=f"name = '{name}'")
            if experiments:
                return cast("str | None", experiments[0].get("experiment_id"))
        except Exception as e:
            logger.warning("MLflow search_experiments failed during get_or_create: %s", e)

        experiment_id = await self.create_experiment(name=name, artifact_location=artifact_location, tags=tags)
        if experiment_id:
            return experiment_id

        # Create failed — most likely RESOURCE_ALREADY_EXISTS because a soft-deleted experiment
        # still holds the name. Restore it and reuse the id (rebind tags to the new job).
        deleted = await self.search_experiments(filter_expr=f"name = '{name}'", view_type="DELETED_ONLY")
        if deleted:
            existing_id = cast("str | None", deleted[0].get("experiment_id"))
            if existing_id and await self.restore_experiment(existing_id):
                if tags:
                    for key, value in tags.items():
                        await self.set_experiment_tag(experiment_id=existing_id, key=key, value=value)
                return existing_id
        return None

    async def terminate_run(self, *, run_id: str, status: str = "KILLED") -> bool:
        """POST /api/2.0/mlflow/runs/update — transition a run to a terminal ``status``.

        Used when a training job is stopped: the training process is killed by the pod
        SIGTERM before it can call ``mlflow.end_run()``, so the run would otherwise stay
        ``RUNNING`` forever on the MLflow server (run lifecycle is client-driven; the server
        never learns the process died). Valid terminal statuses: ``FINISHED``, ``FAILED``,
        ``KILLED``. Sets ``end_time`` so MLflow stops counting it as active.

        Returns True on success, False on failure (callers treat best-effort).
        """
        body: dict[str, Any] = {"run_id": run_id, "status": status, "end_time": int(time.time() * 1000)}
        try:
            resp = await self._client.post("/api/2.0/mlflow/runs/update", json=body)
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("MLflow terminate_run failed for %s: %s", run_id, e)
            return False

    async def delete_experiment(self, experiment_id: str) -> bool:
        """POST /api/2.0/mlflow/experiments/delete — soft-delete an experiment and all its runs.

        Called when a training job is deleted, so the platform does not leave orphan experiment/run
        records in MLflow. MLflow marks the experiment (and every run under it) as deleted — strong
        binding guarantees one job ↔ one experiment, so this is safe. Returns True on success,
        False on failure (callers treat best-effort).
        """
        try:
            resp = await self._client.post("/api/2.0/mlflow/experiments/delete", json={"experiment_id": experiment_id})
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("MLflow delete_experiment failed for %s: %s", experiment_id, e)
            return False

    async def restore_experiment(self, experiment_id: str) -> bool:
        """POST /api/2.0/mlflow/experiments/restore — undo a soft-deleted experiment.

        Reverses ``delete_experiment``: marks ``lifecycle_stage`` back to active. Used by
        ``get_or_create_experiment`` to reclaim a name held by a soft-deleted experiment —
        MLflow reserves deleted experiments' names, so a fresh ``create`` returns
        RESOURCE_ALREADY_EXISTS and the only way to free the name is to restore it. Note:
        restoring the experiment does NOT restore the runs that were deleted with it; they
        stay invisible in active views, so the new job sees a clean experiment. Returns
        True on success, False on failure (callers treat best-effort).
        """
        try:
            resp = await self._client.post("/api/2.0/mlflow/experiments/restore", json={"experiment_id": experiment_id})
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning("MLflow restore_experiment failed for %s: %s", experiment_id, e)
            return False

    async def set_experiment_tag(self, *, experiment_id: str, key: str, value: str) -> bool:
        """POST /api/2.0/mlflow/experiments/set-experiment-tag — set a single experiment tag.

        Used after restoring a soft-deleted experiment to rebind ``kubeai.job_id`` to the
        new training job: the restored experiment otherwise keeps the prior job's tags.
        Returns True on success, False on failure (callers treat best-effort).
        """
        try:
            resp = await self._client.post(
                "/api/2.0/mlflow/experiments/set-experiment-tag",
                json={"experiment_id": experiment_id, "key": key, "value": value},
            )
            resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(
                "MLflow set_experiment_tag failed for experiment %s / key %s: %s",
                experiment_id,
                key,
                e,
            )
            return False
