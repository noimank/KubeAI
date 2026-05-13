from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from app.integrations.mlflow.client import get_mlflow_client
from app.models.dataset import DatasetVersion
from app.models.experiment import Experiment
from app.models.image import Image
from app.models.training_job import TrainingJob

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ExperimentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_experiment(
        self,
        *,
        tenant_id: uuid.UUID,
        training_job_id: uuid.UUID,
        mlflow_experiment_name: str | None = None,
    ) -> Experiment:
        mlflow_client = get_mlflow_client()
        mlflow_experiment_id: str | None = None

        if mlflow_client and mlflow_experiment_name:
            try:
                experiments = await mlflow_client.search_experiments(filter_expr=f"name = '{mlflow_experiment_name}'")
                if experiments:
                    mlflow_experiment_id = experiments[0].get("experiment_id")
            except Exception as e:
                logger.warning("Failed to lookup MLflow experiment: %s", e)

        experiment = Experiment(
            tenant_id=tenant_id,
            training_job_id=training_job_id,
            mlflow_experiment_id=mlflow_experiment_id,
            status="active",
        )
        self.db.add(experiment)
        await self.db.flush()
        return experiment

    async def get_experiments(
        self,
        *,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        training_job_name: str | None = None,
        status: str | None = None,
        sort_by: str | None = None,
        sort_order: str | None = None,
        dataset_id: uuid.UUID | None = None,
        image_id: uuid.UUID | None = None,
        start_date: Any | None = None,
        end_date: Any | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query = select(Experiment).where(Experiment.tenant_id == tenant_id)

        if status:
            query = query.where(Experiment.status == status)
        if training_job_name:
            query = query.join(TrainingJob, Experiment.training_job_id == TrainingJob.id).where(
                TrainingJob.name.ilike(f"%{training_job_name}%")
            )

        # Filter by dataset_id / image_id via TrainingJob
        job_joined = training_job_name is not None
        if dataset_id or image_id:
            if not job_joined:
                query = query.join(TrainingJob, Experiment.training_job_id == TrainingJob.id)
                job_joined = True
            if dataset_id:
                query = query.where(TrainingJob.dataset_id == dataset_id)
            if image_id:
                query = query.where(TrainingJob.image_id == image_id)

        if start_date:
            query = query.where(Experiment.created_at >= start_date)
        if end_date:
            query = query.where(Experiment.created_at <= end_date)

        # Sort by metric requires MLflow data — handle after query
        sort_by_metric = sort_by and sort_by.startswith("metric_")
        if sort_by_metric:
            assert sort_by is not None
            metric_key = sort_by[len("metric_") :]
            # Fetch all matching experiments (limited), then sort in memory
            capped_size = 200
            result = await self.db.execute(query.order_by(Experiment.created_at.desc()).limit(capped_size))
            experiments = list(result.scalars().all())

            mlflow_client = get_mlflow_client()
            items = await self._enrich_experiments_batch(experiments, mlflow_client)

            # Sort by metric latest value
            for item in items:
                metric_val = None
                if item.get("metrics"):
                    for m in item["metrics"]:
                        if m["key"] == metric_key:
                            metric_val = m["value"]
                            break
                item["_metric_sort"] = metric_val

            reverse = sort_order == "desc"
            items.sort(key=lambda x: (x["_metric_sort"] is None, x["_metric_sort"] or 0), reverse=reverse)

            total = len(items)
            start = (page - 1) * page_size
            items = items[start : start + page_size]
            for item in items:
                item.pop("_metric_sort", None)

            return items, total

        # DB-level sorting
        order_col: Any = Experiment.created_at
        if sort_by == "status":
            order_col = Experiment.status
        order_func = order_col.desc() if sort_order == "desc" else order_col.asc()
        if not sort_by:
            order_func = Experiment.created_at.desc()

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(query.order_by(order_func).offset((page - 1) * page_size).limit(page_size))
        experiments = list(result.scalars().all())

        mlflow_client = get_mlflow_client()
        items = await self._enrich_experiments_batch(experiments, mlflow_client)

        return items, total

    async def get_experiment_detail(self, experiment_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(Experiment).where(Experiment.id == experiment_id, Experiment.tenant_id == tenant_id)
        )
        exp = result.scalar_one_or_none()
        if not exp:
            return None

        mlflow_client = get_mlflow_client()
        return await self._enrich_experiment(exp, mlflow_client, include_full_metrics=True)

    async def get_metric_history(
        self,
        experiment_id: uuid.UUID,
        tenant_id: uuid.UUID,
        metric_key: str,
    ) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(Experiment).where(Experiment.id == experiment_id, Experiment.tenant_id == tenant_id)
        )
        exp = result.scalar_one_or_none()
        if not exp:
            return []

        mlflow_client = get_mlflow_client()
        if not mlflow_client:
            return []

        run_data = None
        if exp.mlflow_experiment_id:
            runs = await mlflow_client.search_runs(experiment_ids=[exp.mlflow_experiment_id])
            if runs:
                run_data = runs[0]
        if not run_data and exp.mlflow_run_id:
            run_data = await mlflow_client.get_run(exp.mlflow_run_id)

        if not run_data:
            return []

        run_id = run_data["info"]["run_id"]
        history = await mlflow_client.get_metric_history(run_id=run_id, metric_key=metric_key)

        return [
            {
                "step": p["step"],
                "value": p["value"],
                "timestamp": p["timestamp"] / 1000,
            }
            for p in history
        ]

    async def sync_experiment_status(self, training_job_id: uuid.UUID, job_status: str) -> None:
        result = await self.db.execute(select(Experiment).where(Experiment.training_job_id == training_job_id))
        experiments = list(result.scalars().all())
        if not experiments:
            return

        status_map = {
            "succeeded": "completed",
            "failed": "failed",
            "stopped": "failed",
        }
        new_status = status_map.get(job_status)
        if not new_status:
            return

        for exp in experiments:
            exp.status = new_status

        mlflow_client = get_mlflow_client()
        if mlflow_client:
            for exp in experiments:
                if exp.mlflow_run_id:
                    try:
                        run = await mlflow_client.get_run(exp.mlflow_run_id)
                        if run:
                            run_info = run.get("info", {})
                            run_status = run_info.get("status", "")
                            if run_status == "FINISHED":
                                exp.status = "completed"
                            elif run_status == "FAILED":
                                exp.status = "failed"
                            elif run_status == "RUNNING":
                                exp.status = "active"
                    except Exception as e:
                        logger.warning("Failed to sync MLflow run status for %s: %s", exp.mlflow_run_id, e)

    async def _enrich_experiment(
        self,
        exp: Experiment,
        mlflow_client: Any | None,
        include_full_metrics: bool = False,
    ) -> dict[str, Any]:
        job_result = await self.db.execute(select(TrainingJob).where(TrainingJob.id == exp.training_job_id))
        job = job_result.scalar_one_or_none()

        training_job_name = job.name if job else None
        dataset_version = None
        image_name = None

        if job:
            if job.dataset_version_id:
                dv_result = await self.db.execute(
                    select(DatasetVersion.version_number).where(DatasetVersion.id == job.dataset_version_id)
                )
                dv = dv_result.scalar_one_or_none()
                if dv is not None:
                    dataset_version = f"v{dv}"
            if job.image_id:
                img_result = await self.db.execute(select(Image.name).where(Image.id == job.image_id))
                image_name = img_result.scalar_one_or_none()

        hyperparameters: dict[str, str] | None = None
        metrics: list[dict[str, Any]] | None = None
        metric_histories: dict[str, list[dict[str, Any]]] | None = None

        if mlflow_client:
            hyperparameters, metrics, metric_histories = await self._fetch_mlflow_data(
                mlflow_client, exp, include_full_metrics
            )

        duration_seconds = None
        if job and job.started_at:
            end = job.finished_at or job.started_at
            duration_seconds = int((end - job.started_at).total_seconds())

        training_job_info = None
        if job:
            training_job_info = {
                "id": job.id,
                "name": job.name,
                "command": job.command,
                "dataset_version": dataset_version,
                "image_name": image_name,
                "gpu_count": job.gpu_count,
                "cpu": job.cpu,
                "memory": job.memory,
            }

        return {
            "id": exp.id,
            "tenant_id": exp.tenant_id,
            "training_job_id": exp.training_job_id,
            "training_job_name": training_job_name,
            "mlflow_experiment_id": exp.mlflow_experiment_id,
            "mlflow_run_id": exp.mlflow_run_id,
            "status": exp.status,
            "hyperparameters": hyperparameters,
            "metrics": metrics,
            "dataset_version": dataset_version,
            "image_name": image_name,
            "created_at": exp.created_at,
            "updated_at": exp.updated_at,
            "metric_histories": metric_histories,
            "duration_seconds": duration_seconds,
            "training_job": training_job_info,
        }

    async def _fetch_mlflow_data(
        self,
        mlflow_client: Any,
        exp: Experiment,
        include_full_metrics: bool = False,
    ) -> tuple[dict[str, str] | None, list[dict[str, Any]] | None, dict[str, list[dict[str, Any]]] | None]:
        run_data = None
        if exp.mlflow_experiment_id:
            runs = await mlflow_client.search_runs(experiment_ids=[exp.mlflow_experiment_id])
            if runs:
                run_data = runs[0]
        if not run_data and exp.mlflow_run_id:
            run_data = await mlflow_client.get_run(exp.mlflow_run_id)

        if not run_data:
            return None, None, None

        data = run_data.get("data", {})
        params = {p["key"]: p["value"] for p in data.get("params", [])}
        raw_metrics = data.get("metrics", [])

        metrics_map: dict[str, dict[str, Any]] = {}
        for m in raw_metrics:
            metrics_map[m["key"]] = {"key": m["key"], "value": m["value"]}

        metrics_list = list(metrics_map.values())

        if not include_full_metrics:
            metrics_list = metrics_list[:5]

        # Fetch metric histories for detail view
        metric_histories: dict[str, list[dict[str, Any]]] | None = None
        if include_full_metrics and metrics_map:
            run_id = run_data["info"]["run_id"]
            metric_histories = {}
            history_tasks = [mlflow_client.get_metric_history(run_id=run_id, metric_key=key) for key in metrics_map]
            results = await asyncio.gather(*history_tasks, return_exceptions=True)
            for key, result in zip(metrics_map, results, strict=True):
                if isinstance(result, Exception):
                    logger.warning("Failed to fetch metric history for %s: %s", key, result)
                    continue
                metric_histories[key] = result  # type: ignore[assignment]

        return params if params else None, metrics_list if metrics_list else None, metric_histories

    async def _enrich_experiments_batch(
        self,
        experiments: list[Experiment],
        mlflow_client: Any | None,
    ) -> list[dict[str, Any]]:
        """Batch enrich experiments with a single DB query for related entities."""
        if not experiments:
            return []

        job_ids = [exp.training_job_id for exp in experiments]
        jobs_result = await self.db.execute(select(TrainingJob).where(TrainingJob.id.in_(job_ids)))
        jobs_by_id: dict[Any, TrainingJob] = {j.id: j for j in jobs_result.scalars().all()}

        dv_ids = [j.dataset_version_id for j in jobs_by_id.values() if j.dataset_version_id]
        img_ids = [j.image_id for j in jobs_by_id.values() if j.image_id]

        dv_map: dict[Any, int] = {}
        if dv_ids:
            dv_result = await self.db.execute(
                select(DatasetVersion.id, DatasetVersion.version_number).where(DatasetVersion.id.in_(dv_ids))
            )
            for row in dv_result.all():
                dv_map[row[0]] = row[1]

        img_map: dict[Any, str] = {}
        if img_ids:
            img_result = await self.db.execute(select(Image.id, Image.name).where(Image.id.in_(img_ids)))
            for img_row in img_result.all():
                img_map[img_row[0]] = img_row[1]

        items: list[dict[str, Any]] = []
        for exp in experiments:
            job = jobs_by_id.get(exp.training_job_id)
            training_job_name = job.name if job else None
            dataset_version = None
            image_name = None

            if job:
                if job.dataset_version_id and job.dataset_version_id in dv_map:
                    dataset_version = f"v{dv_map[job.dataset_version_id]}"
                if job.image_id and job.image_id in img_map:
                    image_name = img_map[job.image_id]

            hyperparameters: dict[str, str] | None = None
            metrics: list[dict[str, Any]] | None = None
            if mlflow_client:
                hyperparameters, metrics, _ = await self._fetch_mlflow_data(mlflow_client, exp)

            items.append(
                {
                    "id": exp.id,
                    "tenant_id": exp.tenant_id,
                    "training_job_id": exp.training_job_id,
                    "training_job_name": training_job_name,
                    "mlflow_experiment_id": exp.mlflow_experiment_id,
                    "mlflow_run_id": exp.mlflow_run_id,
                    "status": exp.status,
                    "hyperparameters": hyperparameters,
                    "metrics": metrics,
                    "dataset_version": dataset_version,
                    "image_name": image_name,
                    "created_at": exp.created_at,
                    "updated_at": exp.updated_at,
                }
            )

        return items

    async def compare_experiments(
        self,
        tenant_id: uuid.UUID,
        experiment_ids: list[uuid.UUID],
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(Experiment).where(
                Experiment.tenant_id == tenant_id,
                Experiment.id.in_(experiment_ids),
            )
        )
        experiments = list(result.scalars().all())

        if len(experiments) < 2:
            return None

        mlflow_client = get_mlflow_client()

        # Batch enrich for basic info
        items = await self._enrich_experiments_batch(experiments, mlflow_client)

        # Collect hyperparameters from TrainingJob (primary) and MLflow params (fallback)
        job_ids = [exp.training_job_id for exp in experiments]
        jobs_result = await self.db.execute(select(TrainingJob).where(TrainingJob.id.in_(job_ids)))
        jobs_by_id = {j.id: j for j in jobs_result.scalars().all()}

        # Build hyperparam comparison
        all_keys: set[str] = set()
        hp_per_exp: dict[str, dict[str, str | None]] = {}
        for item in items:
            job = jobs_by_id.get(item["training_job_id"])
            hp: dict[str, str | None] = {}
            if job and job.hyperparameters:
                hp.update(job.hyperparameters)
            elif item.get("hyperparameters"):
                hp.update(item["hyperparameters"])
            all_keys.update(hp.keys())
            hp_per_exp[str(item["id"])] = hp

        hyperparams_diff: list[dict[str, Any]] = []
        for key in sorted(all_keys):
            values: dict[str, str | None] = {}
            for exp_id_str, hp in hp_per_exp.items():
                values[exp_id_str] = hp.get(key)
            present_values = [v for v in values.values() if v is not None]
            is_different = len(present_values) > 1 and len(set(present_values)) > 1
            hyperparams_diff.append(
                {
                    "key": key,
                    "values": values,
                    "is_different": is_different,
                }
            )

        # Build metric comparison
        metrics_comparison: list[dict[str, Any]] = []
        if mlflow_client:
            metric_keys_per_exp: dict[str, set[str]] = {}
            run_data_cache: dict[str, dict[str, Any] | None] = {}

            for exp in experiments:
                exp_id_str = str(exp.id)
                run_data = None
                if exp.mlflow_experiment_id:
                    runs = await mlflow_client.search_runs(experiment_ids=[exp.mlflow_experiment_id])
                    if runs:
                        run_data = runs[0]
                if not run_data and exp.mlflow_run_id:
                    run_data = await mlflow_client.get_run(exp.mlflow_run_id)

                run_data_cache[exp_id_str] = run_data
                if run_data:
                    raw_metrics = run_data.get("data", {}).get("metrics", [])
                    metric_keys_per_exp[exp_id_str] = {m["key"] for m in raw_metrics}
                else:
                    metric_keys_per_exp[exp_id_str] = set()

            all_metric_keys: set[str] = set()
            for keys in metric_keys_per_exp.values():
                all_metric_keys.update(keys)

            # Fetch metric histories concurrently
            for mkey in sorted(all_metric_keys):
                series: dict[str, list[dict[str, Any]]] = {}
                fetch_tasks = []
                exp_ids_for_key = []

                for exp in experiments:
                    exp_id_str = str(exp.id)
                    if mkey not in metric_keys_per_exp.get(exp_id_str, set()):
                        continue
                    run_data = run_data_cache.get(exp_id_str)
                    if not run_data:
                        continue
                    run_id = run_data["info"]["run_id"]
                    fetch_tasks.append(mlflow_client.get_metric_history(run_id=run_id, metric_key=mkey))
                    exp_ids_for_key.append(exp_id_str)

                if fetch_tasks:
                    gather_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                    for eid, res in zip(exp_ids_for_key, gather_results, strict=True):
                        if isinstance(res, Exception):
                            logger.warning("Failed to fetch metric history for %s: %s", mkey, res)
                            continue
                        series[eid] = res  # type: ignore[assignment]

                if series:
                    metrics_comparison.append(
                        {
                            "metric_key": mkey,
                            "series": series,
                        }
                    )

        return {
            "experiments": items,
            "hyperparams_diff": hyperparams_diff,
            "metrics_comparison": metrics_comparison,
        }
