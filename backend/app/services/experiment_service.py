from __future__ import annotations

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
    ) -> tuple[list[dict[str, Any]], int]:
        query = select(Experiment).where(Experiment.tenant_id == tenant_id)

        if status:
            query = query.where(Experiment.status == status)
        if training_job_name:
            query = query.join(TrainingJob, Experiment.training_job_id == TrainingJob.id).where(
                TrainingJob.name.ilike(f"%{training_job_name}%")
            )

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()

        result = await self.db.execute(
            query.order_by(Experiment.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        experiments = list(result.scalars().all())

        items: list[dict[str, Any]] = []
        mlflow_client = get_mlflow_client()

        for exp in experiments:
            item = await self._enrich_experiment(exp, mlflow_client)
            items.append(item)

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
        # Get training job info
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

        # Get hyperparameters and metrics from MLflow
        hyperparameters: dict[str, str] | None = None
        metrics: list[dict[str, Any]] | None = None

        if mlflow_client:
            hyperparameters, metrics = await self._fetch_mlflow_data(mlflow_client, exp, include_full_metrics)

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
        }

    async def _fetch_mlflow_data(
        self,
        mlflow_client: Any,
        exp: Experiment,
        include_full_metrics: bool = False,
    ) -> tuple[dict[str, str] | None, list[dict[str, Any]] | None]:
        # Try to find runs by experiment ID
        run_data = None
        if exp.mlflow_experiment_id:
            runs = await mlflow_client.search_runs(experiment_ids=[exp.mlflow_experiment_id])
            if runs:
                run_data = runs[0]
        if not run_data and exp.mlflow_run_id:
            run_data = await mlflow_client.get_run(exp.mlflow_run_id)

        if not run_data:
            return None, None

        data = run_data.get("data", {})
        params = {p["key"]: p["value"] for p in data.get("params", [])}
        raw_metrics = data.get("metrics", [])

        # Deduplicate metrics: keep latest value per key
        metrics_map: dict[str, dict[str, Any]] = {}
        for m in raw_metrics:
            metrics_map[m["key"]] = {"key": m["key"], "value": m["value"]}

        metrics_list = list(metrics_map.values())

        if not include_full_metrics:
            metrics_list = metrics_list[:5]

        return params if params else None, metrics_list if metrics_list else None
