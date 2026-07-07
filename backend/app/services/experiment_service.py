from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.clients import get_mlflow_client
from app.models.dataset import DatasetVersion
from app.models.experiment import Experiment
from app.models.image import Image
from app.models.training_job import TrainingJob

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# TrainingJob 终态 → Experiment 状态的权威映射. 训练任务状态是平台事实源, experiment 状态
# 跟随它而非跟随 MLflow run 状态 (run 生命周期是客户端驱动的, 被强杀时不会自行终结).
# 注: stopped 暂映射为 failed; 引入独立 "stopped" 状态与前端/TrainingJob 对齐是后续优化.
_JOB_TO_EXP_STATUS = {
    "succeeded": "completed",
    "failed": "failed",
    "stopped": "failed",
}


class ExperimentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_experiment(
        self,
        *,
        tenant_id: uuid.UUID,
        training_job_id: uuid.UUID,
        mlflow_experiment_name: str,
    ) -> Experiment:
        """预创建 MLflow experiment + run, 写入 Experiment 记录, 返回含 run_id 的记录.

        平台预创建 run 并把 run_id 落库, 同时由调用方将其注入容器 ``MLFLOW_RUN_ID``;
        训练脚本 ``mlflow.start_run(run_id=...)`` 恢复该 run —— 形成 job↔run 1:1 强绑定.
        Volcano 重试时 env 不变, 脚本 resume 同一 run, 不再产生多 run.

        幂等: 同一 ``training_job_id`` 已有记录则直接返回, 不重复创建 MLflow experiment/run.
        覆盖两类场景 ——
          1. 提交重试: 上次 ``create_vcjob`` 失败但 Experiment 已被调用方 commit 持久化,
             重试时此处 SELECT 命中并短路, 避免重复 MLflow run 与重复 DB 行.
          2. 并发提交 (Taskiq at-least-once): 唯一约束在 flush 时拒绝重复, 回滚后取回先入库的记录.

        experiment 与 run 创建都幂等/可重入失败即抛错 (fail-fast): MLflow 不可达时不提交 VCJob,
        避免留下半截状态.

        Raises:
            RuntimeError: MLflow experiment 或 run 创建失败
        """
        # 幂等短路: 重试/并发场景下已存在的记录直接复用.
        existing = await self.db.execute(select(Experiment).where(Experiment.training_job_id == training_job_id))
        if (experiment := existing.scalar_one_or_none()) is not None:
            return experiment

        mlflow_client = get_mlflow_client()

        experiment_id = await mlflow_client.get_or_create_experiment(
            name=mlflow_experiment_name,
            tags={"kubeai.job_id": str(training_job_id), "kubeai.tenant_id": str(tenant_id)},
        )
        if not experiment_id:
            raise RuntimeError(f"无法创建 MLflow experiment: {mlflow_experiment_name}")

        run_id = await mlflow_client.create_run(
            experiment_id=experiment_id,
            run_name=mlflow_experiment_name,
            tags={"kubeai.job_id": str(training_job_id), "kubeai.tenant_id": str(tenant_id)},
        )
        if not run_id:
            raise RuntimeError(f"无法创建 MLflow run: {mlflow_experiment_name}")

        experiment = Experiment(
            tenant_id=tenant_id,
            training_job_id=training_job_id,
            mlflow_experiment_id=experiment_id,
            mlflow_run_id=run_id,
            status="active",
        )
        self.db.add(experiment)
        try:
            await self.db.flush()
        except IntegrityError:
            # 并发竞态: 另一事务抢先插入同一 training_job_id, 回滚后取回其记录.
            await self.db.rollback()
            result = await self.db.execute(select(Experiment).where(Experiment.training_job_id == training_job_id))
            experiment = result.scalar_one()
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

            items = await self._enrich_experiments_batch(experiments)

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

        items = await self._enrich_experiments_batch(experiments)

        return items, total

    async def get_experiment_detail(self, experiment_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(Experiment).where(Experiment.id == experiment_id, Experiment.tenant_id == tenant_id)
        )
        exp = result.scalar_one_or_none()
        if not exp:
            return None

        return await self._enrich_experiment(exp, include_full_metrics=True)

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

        run = await self._latest_run(exp)
        if not run:
            return []
        run_id = run.get("info", {}).get("run_id")
        if not run_id:
            return []

        mlflow_client = get_mlflow_client()
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
        """训练任务到达终态时, 同步其 experiment 状态.

        **权威源是 TrainingJob 状态, 不是 MLflow run 状态**. MLflow 的 run 生命周期是
        客户端驱动的: 训练 Pod 被 SIGTERM 强杀时脚本来不及调 ``mlflow.end_run()``,
        run 会永远停在 ``RUNNING``, 所以绝不能用 run 状态反推平台状态 (旧实现正是因此
        把已停止任务的 experiment 锁死在 "active").

        流程: 先按训练任务状态定终态, 再解析 latest run 用于
          1. 回填 ``mlflow_run_id`` (后续读/直链/终止都受益)
          2. 细化失败语义 —— run 侧 ``FAILED`` (如 OOM) 比任务状态更精确

        非终态 job_status (running 等) 直接跳过, 不触碰 MLflow.
        """
        result = await self.db.execute(select(Experiment).where(Experiment.training_job_id == training_job_id))
        experiments = list(result.scalars().all())
        if not experiments:
            return

        new_status = _JOB_TO_EXP_STATUS.get(job_status)
        if not new_status:
            return

        for exp in experiments:
            # ① 训练任务状态为权威源: 直接定终态.
            exp.status = new_status

            run = await self._latest_run(exp)
            # ② MLflow 侧明确失败 → failed (比任务状态更精确, 如评估阶段 OOM 被 run 记录).
            # 刻意没有 RUNNING→active 回滚: 任务既已终态, run 仍 RUNNING 必是被强杀的僵尸
            # run, 不应复活状态. 强绑定下 run_id 创建时已落库, 无需在此回填.
            if run and run.get("info", {}).get("status", "") == "FAILED":
                exp.status = "failed"

    async def terminate_experiments_for_job(self, training_job_id: uuid.UUID) -> None:
        """训练任务被停止时, 主动把其 experiment 绑定的 run 在 MLflow 侧置为 ``KILLED``.

        训练 Pod 收到 SIGTERM 被强杀, 脚本来不及执行 ``mlflow.end_run()``, run 会永远停在
        ``RUNNING``. 本方法在删除 VCJob 之前调用, 通过 ``runs/update`` 主动终结 run, 避免:
          1. MLflow 里堆积永远 ``RUNNING`` 的僵尸 run
          2. 后续 ``sync_experiment_status`` 把刚设好的终态又覆盖回 active

        强绑定下 run_id 在创建时已落库, 直接用它终止 (无需先 search/回填).
        Best-effort: MLflow 不可达或 run 不存在仅 warning, 不影响停止流程.
        """
        result = await self.db.execute(select(Experiment).where(Experiment.training_job_id == training_job_id))
        experiments = list(result.scalars().all())
        if not experiments:
            return

        mlflow_client = get_mlflow_client()
        for exp in experiments:
            if not exp.mlflow_run_id:
                continue
            await mlflow_client.terminate_run(run_id=exp.mlflow_run_id, status="KILLED")

    async def delete_experiment(self, mlflow_experiment_id: str) -> None:
        """删除 MLflow experiment (软删除, 连带其下所有 run).

        训练任务删除时调用, 清理 MLflow 侧数据避免孤儿 experiment/run. 强绑定保证
        一个 job 对应一个独立 experiment, 删除安全. Best-effort: 失败仅 warning.
        """
        if not mlflow_experiment_id:
            return
        await get_mlflow_client().delete_experiment(mlflow_experiment_id)

    async def _enrich_experiment(
        self,
        exp: Experiment,
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

        hyperparameters, metrics, metric_histories = await self._fetch_mlflow_data(exp, include_full_metrics)

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
                "dataset_id": job.dataset_id,
                "dataset_version_id": job.dataset_version_id,
                "image_id": job.image_id,
                "gpu_mode": job.gpu_mode,
                "worker_count": job.worker_count,
                "priority": job.priority,
                "mlflow_enabled": job.mlflow_enabled,
                "tensorboard_enabled": job.tensorboard_enabled,
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

    async def _latest_run(self, exp: Experiment) -> dict[str, Any] | None:
        """Resolve the MLflow run bound to this experiment by its stored ``mlflow_run_id``.

        Strong binding: ``mlflow_run_id`` is set at experiment-creation time (the platform
        pre-creates the run and injects it as ``MLFLOW_RUN_ID``). There is no search fallback
        — a missing/None run_id means no binding (e.g. rows created before this contract, or
        the run was deleted server-side).

        Returns ``None`` when there is no bound run.
        """
        if not exp.mlflow_run_id:
            return None
        return await get_mlflow_client().get_run(exp.mlflow_run_id)

    async def _fetch_mlflow_data(
        self,
        exp: Experiment,
        include_full_metrics: bool = False,
    ) -> tuple[dict[str, str] | None, list[dict[str, Any]] | None, dict[str, list[dict[str, Any]]] | None]:
        """Fetch params + latest metrics (+ full histories) for an Experiment's latest run."""
        if not exp.mlflow_run_id and not exp.mlflow_experiment_id:
            return None, None, None

        run_data = await self._latest_run(exp)
        if not run_data:
            return None, None, None

        mlflow_client = get_mlflow_client()
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

    async def _batch_fetch_mlflow_data(
        self, experiments: list[Experiment]
    ) -> dict[uuid.UUID, tuple[dict[str, str] | None, list[dict[str, Any]] | None]]:
        """一次 search_runs 批量获取所有 experiment 的 run (超参 + 最新指标), 替代 N 次串行 get_run.

        列表页性能关键路径: 强绑定下每个 experiment 恰好一个 run, search_runs(experiment_ids=[...])
        一次拿回全部, 按 experiment_id 映射. MLflow 不可达时 search_runs 返回 [], 列表降级为只显示
        DB 字段.
        """
        exp_ids = [exp.mlflow_experiment_id for exp in experiments if exp.mlflow_experiment_id]
        if not exp_ids:
            return {exp.id: (None, None) for exp in experiments}

        runs = await get_mlflow_client().search_runs(experiment_ids=exp_ids, max_results=len(exp_ids))
        run_by_exp: dict[str, dict[str, Any]] = {run["info"]["experiment_id"]: run for run in runs}

        result: dict[uuid.UUID, tuple[dict[str, str] | None, list[dict[str, Any]] | None]] = {}
        for exp in experiments:
            run = run_by_exp.get(exp.mlflow_experiment_id) if exp.mlflow_experiment_id else None
            data = run.get("data", {}) if run else {}
            params = {p["key"]: p["value"] for p in data.get("params", [])} or None
            metrics = [{"key": m["key"], "value": m["value"]} for m in data.get("metrics", [])][:5] or None
            result[exp.id] = (params, metrics)
        return result

    async def _enrich_experiments_batch(
        self,
        experiments: list[Experiment],
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

        mlflow_data = await self._batch_fetch_mlflow_data(experiments)

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

            hyperparameters, metrics = mlflow_data.get(exp.id, (None, None))

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

        items = await self._enrich_experiments_batch(experiments)

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
        mlflow_client = get_mlflow_client()
        metric_keys_per_exp: dict[str, set[str]] = {}
        run_data_cache: dict[str, dict[str, Any] | None] = {}

        for exp in experiments:
            exp_id_str = str(exp.id)
            run_data = await self._latest_run(exp)

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
