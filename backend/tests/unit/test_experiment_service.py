import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.experiment import Experiment
from app.services.experiment_service import ExperimentService


def _make_experiment(**overrides):
    defaults = {
        "tenant_id": uuid.uuid4(),
        "training_job_id": uuid.uuid4(),
        "mlflow_experiment_id": None,
        "mlflow_run_id": None,
        "status": "active",
    }
    defaults.update(overrides)
    exp = Experiment(**defaults)
    exp.created_at = MagicMock()
    exp.updated_at = MagicMock()
    return exp


def _mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    # Result 对象须是同步 MagicMock: 否则 .scalar_one_or_none() 会被当作 AsyncMock 返回协程.
    db.execute.return_value = MagicMock()
    db.rollback = AsyncMock()
    # 默认: 幂等 SELECT 查无已存在记录, 走创建分支 (create_experiment 首行 SELECT).
    db.execute.return_value.scalar_one_or_none.return_value = None
    return db


class TestCreateExperiment:
    async def test_create_experiment_creates_experiment_and_run(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_or_create_experiment.return_value = "42"
        mlflow_client.create_run.return_value = "run-1"

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            db = _mock_db()
            service = ExperimentService(db)
            tenant_id = uuid.uuid4()
            job_id = uuid.uuid4()

            exp = await service.create_experiment(
                tenant_id=tenant_id,
                training_job_id=job_id,
                mlflow_experiment_name="kubeai-abc-my-job",
            )

            assert exp.tenant_id == tenant_id
            assert exp.training_job_id == job_id
            assert exp.mlflow_experiment_id == "42"
            assert exp.mlflow_run_id == "run-1"  # 预创建 run 并落库 (强绑定)
            assert exp.status == "active"
            # experiment 创建 kwargs
            gc_kwargs = mlflow_client.get_or_create_experiment.await_args.kwargs
            assert gc_kwargs["name"] == "kubeai-abc-my-job"
            assert gc_kwargs["tags"]["kubeai.job_id"] == str(job_id)
            assert gc_kwargs["tags"]["kubeai.tenant_id"] == str(tenant_id)
            # run 创建 kwargs: experiment_id + run_name + tags
            cr_kwargs = mlflow_client.create_run.await_args.kwargs
            assert cr_kwargs["experiment_id"] == "42"
            assert cr_kwargs["run_name"] == "kubeai-abc-my-job"
            assert cr_kwargs["tags"]["kubeai.job_id"] == str(job_id)
            db.add.assert_called_once()
            db.flush.assert_awaited_once()

    async def test_create_experiment_experiment_creation_fails_raises(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_or_create_experiment.return_value = None

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(_mock_db())

            with pytest.raises(RuntimeError, match="无法创建 MLflow experiment"):
                await service.create_experiment(
                    tenant_id=uuid.uuid4(),
                    training_job_id=uuid.uuid4(),
                    mlflow_experiment_name="kubeai-x",
                )

    async def test_create_experiment_run_creation_fails_raises(self):
        """experiment 建好但 run 创建失败 → fail-fast raise, 不留半截状态."""
        mlflow_client = AsyncMock()
        mlflow_client.get_or_create_experiment.return_value = "42"
        mlflow_client.create_run.return_value = None

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(_mock_db())

            with pytest.raises(RuntimeError, match="无法创建 MLflow run"):
                await service.create_experiment(
                    tenant_id=uuid.uuid4(),
                    training_job_id=uuid.uuid4(),
                    mlflow_experiment_name="kubeai-x",
                )

    async def test_create_experiment_returns_existing_without_mlflow_calls(self):
        """幂等短路: 同一 training_job_id 已有记录 (重试时上次失败已 commit 持久化) → 直接返回, 不再调 MLflow."""
        job_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        existing = _make_experiment(
            training_job_id=job_id, tenant_id=tenant_id, mlflow_experiment_id="42", mlflow_run_id="run-1"
        )
        mlflow_client = AsyncMock()

        db = _mock_db()
        db.execute.return_value.scalar_one_or_none.return_value = existing

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            exp = await service.create_experiment(
                tenant_id=tenant_id,
                training_job_id=job_id,
                mlflow_experiment_name="kubeai-abc-my-job",
            )

        assert exp is existing  # 复用既有记录, 不新建
        mlflow_client.get_or_create_experiment.assert_not_called()
        mlflow_client.create_run.assert_not_called()
        db.add.assert_not_called()
        db.flush.assert_not_called()

    async def test_create_experiment_reselects_on_concurrent_insert(self):
        """并发竞态: flush 撞唯一约束 → 回滚并取回先入库的记录 (Taskiq at-least-once 兜底)."""
        job_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        winner = _make_experiment(
            training_job_id=job_id, tenant_id=tenant_id, mlflow_experiment_id="42", mlflow_run_id="run-1"
        )
        mlflow_client = AsyncMock()
        mlflow_client.get_or_create_experiment.return_value = "42"
        mlflow_client.create_run.return_value = "run-2"

        db = _mock_db()
        # 第一次 execute (幂等 SELECT) → None; flush 抛 IntegrityError; 第二次 execute (re-SELECT) → winner.
        db.execute.side_effect = [
            MagicMock(scalar_one_or_none=MagicMock(return_value=None)),
            MagicMock(scalar_one=MagicMock(return_value=winner)),
        ]
        db.flush.side_effect = IntegrityError("INSERT INTO experiments", {}, Exception("duplicate key"))

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            exp = await service.create_experiment(
                tenant_id=tenant_id,
                training_job_id=job_id,
                mlflow_experiment_name="kubeai-abc-my-job",
            )

        assert exp is winner  # 取回竞态中先入库的记录
        db.rollback.assert_awaited_once()


class TestGetExperiments:
    async def test_get_experiments_returns_empty(self):
        db = _mock_db()
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [total_result, list_result]

        service = ExperimentService(db)
        mlflow_client = AsyncMock()
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            items, total = await service.get_experiments(tenant_id=uuid.uuid4())

        assert items == []
        assert total == 0

    async def test_get_experiments_with_dataset_filter(self):
        db = _mock_db()
        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        exp = _make_experiment()
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [exp]
        # get_experiments uses _enrich_experiments_batch which queries jobs
        job_result = MagicMock()
        job_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [total_result, list_result, job_result]

        service = ExperimentService(db)
        dataset_id = uuid.uuid4()
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = None  # no MLflow data
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            items, total = await service.get_experiments(tenant_id=exp.tenant_id, dataset_id=dataset_id)

        assert total == 1
        assert len(items) == 1

    async def test_get_experiments_with_date_filter(self):
        db = _mock_db()
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [total_result, list_result]

        service = ExperimentService(db)
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)
        mlflow_client = AsyncMock()
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            items, total = await service.get_experiments(
                tenant_id=uuid.uuid4(),
                start_date=start,
                end_date=end,
            )

        assert items == []
        assert total == 0

    async def test_get_experiments_batch_fetches_mlflow_via_search_runs(self):
        """列表用 search_runs 一次批量拿所有 run, 而非 N 次串行 get_run."""
        db = _mock_db()
        total_result = MagicMock()
        total_result.scalar_one.return_value = 1
        exp = _make_experiment(mlflow_experiment_id="mlflow-exp-1", mlflow_run_id="run-1")
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = [exp]
        job_result = MagicMock()
        job_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [total_result, list_result, job_result]

        mlflow_client = AsyncMock()
        mlflow_client.search_runs.return_value = [
            {
                "info": {"experiment_id": "mlflow-exp-1", "run_id": "run-1", "start_time": 1},
                "data": {
                    "params": [{"key": "lr", "value": "0.01"}],
                    "metrics": [{"key": "loss", "value": 0.3}],
                },
            }
        ]
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            items, total = await service.get_experiments(tenant_id=exp.tenant_id)

        assert total == 1
        assert items[0]["hyperparameters"] == {"lr": "0.01"}
        assert items[0]["metrics"] == [{"key": "loss", "value": 0.3}]
        # 一次 search_runs 拿全部, 不调 get_run
        mlflow_client.search_runs.assert_awaited_once()
        mlflow_client.get_run.assert_not_called()


class TestGetMetricHistory:
    async def test_get_metric_history_no_run_id_returns_empty(self):
        db = _mock_db()
        exp = _make_experiment(mlflow_run_id=None, mlflow_experiment_id=None)
        result = MagicMock()
        result.scalar_one_or_none.return_value = exp
        db.execute.return_value = result

        service = ExperimentService(db)
        points = await service.get_metric_history(exp.id, exp.tenant_id, "loss")
        assert points == []

    async def test_get_metric_history_experiment_not_found(self):
        db = _mock_db()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        service = ExperimentService(db)
        points = await service.get_metric_history(uuid.uuid4(), uuid.uuid4(), "loss")
        assert points == []

    async def test_get_metric_history_returns_points(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = {
            "info": {"run_id": "run-abc", "status": "RUNNING"},
            "data": {},
        }
        mlflow_client.get_metric_history.return_value = [
            {"step": 1, "value": 0.8, "timestamp": 1700000000000},
            {"step": 2, "value": 0.5, "timestamp": 1700000060000},
        ]
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            db = _mock_db()
            exp = _make_experiment(mlflow_run_id="run-abc", mlflow_experiment_id="mlflow-exp-1")
            result = MagicMock()
            result.scalar_one_or_none.return_value = exp
            db.execute.return_value = result

            service = ExperimentService(db)
            points = await service.get_metric_history(exp.id, exp.tenant_id, "loss")

            assert len(points) == 2
            assert points[0]["step"] == 1
            assert points[0]["value"] == 0.8
            assert points[0]["timestamp"] == 1700000000.0
            mlflow_client.get_metric_history.assert_awaited_once_with(run_id="run-abc", metric_key="loss")


class TestCompareExperiments:
    async def test_compare_with_less_than_2_experiments(self):
        mlflow_client = AsyncMock()
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            db = _mock_db()
            result = MagicMock()
            result.scalars.return_value.all.return_value = [_make_experiment()]
            db.execute.return_value = result

            service = ExperimentService(db)
            out = await service.compare_experiments(uuid.uuid4(), [uuid.uuid4()])
            assert out is None

    async def test_compare_with_2_experiments_no_mlflow_data(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = None

        tenant_id = uuid.uuid4()
        exp1 = _make_experiment(tenant_id=tenant_id)
        exp2 = _make_experiment(tenant_id=tenant_id)

        db = _mock_db()
        exp_result = MagicMock()
        exp_result.scalars.return_value.all.return_value = [exp1, exp2]
        job_result = MagicMock()
        job_result.scalars.return_value.all.return_value = []
        hp_job_result = MagicMock()
        hp_job_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [exp_result, job_result, hp_job_result]

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            out = await service.compare_experiments(tenant_id, [exp1.id, exp2.id])

        assert out is not None
        assert len(out["experiments"]) == 2
        assert out["hyperparams_diff"] == []
        assert out["metrics_comparison"] == []

    async def test_compare_with_hyperparams_diff(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = None

        tenant_id = uuid.uuid4()
        job1_id = uuid.uuid4()
        job2_id = uuid.uuid4()
        exp1 = _make_experiment(tenant_id=tenant_id, training_job_id=job1_id)
        exp2 = _make_experiment(tenant_id=tenant_id, training_job_id=job2_id)

        mock_job1 = MagicMock()
        mock_job1.id = job1_id
        mock_job1.hyperparameters = {"lr": "0.01", "epochs": "10"}
        mock_job1.dataset_version_id = None
        mock_job1.image_id = None

        mock_job2 = MagicMock()
        mock_job2.id = job2_id
        mock_job2.hyperparameters = {"lr": "0.001", "epochs": "10", "batch_size": "32"}
        mock_job2.dataset_version_id = None
        mock_job2.image_id = None

        db = _mock_db()
        exp_result = MagicMock()
        exp_result.scalars.return_value.all.return_value = [exp1, exp2]
        job_result = MagicMock()
        job_result.scalars.return_value.all.return_value = [mock_job1, mock_job2]
        hp_job_result = MagicMock()
        hp_job_result.scalars.return_value.all.return_value = [mock_job1, mock_job2]

        db.execute.side_effect = [exp_result, job_result, hp_job_result]

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            out = await service.compare_experiments(tenant_id, [exp1.id, exp2.id])

        assert out is not None
        diff_map = {d["key"]: d for d in out["hyperparams_diff"]}
        assert diff_map["lr"]["is_different"] is True
        assert diff_map["epochs"]["is_different"] is False
        assert diff_map["batch_size"]["is_different"] is False


class TestSyncExperimentStatus:
    async def test_sync_to_completed(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = None  # not consulted for this branch
        exp = _make_experiment(status="active")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.sync_experiment_status(exp.training_job_id, "succeeded")

        assert exp.status == "completed"

    async def test_sync_to_failed(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = None
        exp = _make_experiment(status="active")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.sync_experiment_status(exp.training_job_id, "failed")

        assert exp.status == "failed"

    async def test_sync_no_experiments(self):
        mlflow_client = AsyncMock()
        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.sync_experiment_status(uuid.uuid4(), "succeeded")

    async def test_sync_running_job_ignored(self):
        mlflow_client = AsyncMock()
        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.sync_experiment_status(uuid.uuid4(), "running")

    async def test_sync_uses_run_id_directly(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = {
            "info": {"status": "FINISHED", "run_id": "abc"},
        }

        exp = _make_experiment(status="active", mlflow_run_id="abc", mlflow_experiment_id="mlflow-exp-1")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.sync_experiment_status(exp.training_job_id, "succeeded")

        assert exp.status == "completed"
        # 优先用 mlflow_run_id, 不走 search_runs 兜底
        mlflow_client.get_run.assert_awaited_once_with("abc")
        mlflow_client.search_runs.assert_not_called()

    async def test_sync_stopped_with_running_run_does_not_revert_to_active(self):
        """P0 回归: 任务被停止 → Pod 被 SIGTERM 强杀, MLflow run 仍 RUNNING.

        旧实现按 run 状态把 experiment 覆盖回 active, 导致停止的实验永远显示"运行中".
        新实现以训练任务状态为权威源, 保持 failed. 强绑定下 run_id 已落库, _latest_run 走 get_run.
        """
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = {
            "info": {"status": "RUNNING", "run_id": "run-xyz"},
        }
        exp = _make_experiment(status="active", mlflow_run_id="run-xyz", mlflow_experiment_id="mlflow-exp-1")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.sync_experiment_status(exp.training_job_id, "stopped")

        assert exp.status == "failed"  # 不再被回滚成 active
        assert exp.mlflow_run_id == "run-xyz"  # 强绑定: run_id 不变

    async def test_sync_failed_refined_by_mlflow_run_failed(self):
        """任务 succeeded 但 MLflow run 被标 FAILED (如评估阶段 OOM) → experiment failed."""
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = {
            "info": {"status": "FAILED", "run_id": "run-abc"},
        }
        exp = _make_experiment(status="active", mlflow_run_id="run-abc", mlflow_experiment_id="mlflow-exp-1")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.sync_experiment_status(exp.training_job_id, "succeeded")

        assert exp.status == "failed"  # run FAILED 细化覆盖了 completed


class TestTerminateExperimentsForJob:
    async def test_terminate_calls_terminate_run_with_killed(self):
        """停止任务 → 用落库 run_id 直接 KILL (强绑定, 无需先 get_run/search)."""
        mlflow_client = AsyncMock()
        exp = _make_experiment(mlflow_run_id="run-1", mlflow_experiment_id="mlflow-exp-1")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.terminate_experiments_for_job(exp.training_job_id)

        mlflow_client.terminate_run.assert_awaited_once_with(run_id="run-1", status="KILLED")
        mlflow_client.get_run.assert_not_called()

    async def test_terminate_no_experiments_returns_early(self):
        mlflow_client = AsyncMock()
        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.terminate_experiments_for_job(uuid.uuid4())

        mlflow_client.terminate_run.assert_not_called()

    async def test_terminate_skips_when_no_run_id(self):
        """experiment 无落库 run_id → 跳过 terminate (强绑定下正常情况不会发生)."""
        mlflow_client = AsyncMock()
        exp = _make_experiment(mlflow_run_id=None, mlflow_experiment_id="mlflow-exp-1")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(db)
            await service.terminate_experiments_for_job(exp.training_job_id)

        mlflow_client.terminate_run.assert_not_called()


class TestDeleteExperiment:
    async def test_delete_experiment_calls_client(self):
        mlflow_client = AsyncMock()
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(_mock_db())
            await service.delete_experiment("exp-42")

        mlflow_client.delete_experiment.assert_awaited_once_with("exp-42")

    async def test_delete_experiment_skips_when_empty(self):
        mlflow_client = AsyncMock()
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            service = ExperimentService(_mock_db())
            await service.delete_experiment("")

        mlflow_client.delete_experiment.assert_not_called()


class TestEnrichExperimentNewFields:
    async def test_enrich_includes_new_uuid_fields(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = None
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            db = _mock_db()
            job_id = uuid.uuid4()
            dataset_id = uuid.uuid4()
            dataset_version_id = uuid.uuid4()
            image_id = uuid.uuid4()
            exp = _make_experiment(training_job_id=job_id)

            mock_job = MagicMock()
            mock_job.id = job_id
            mock_job.name = "test-job"
            mock_job.command = "python train.py"
            mock_job.dataset_id = dataset_id
            mock_job.dataset_version_id = dataset_version_id
            mock_job.image_id = image_id
            mock_job.gpu_count = 2
            mock_job.gpu_mode = "exclusive"
            mock_job.cpu = "8"
            mock_job.memory = "16Gi"
            mock_job.priority = "high"
            mock_job.worker_count = 4
            mock_job.mlflow_enabled = True
            mock_job.tensorboard_enabled = False
            mock_job.started_at = None

            job_result = MagicMock()
            job_result.scalar_one_or_none.return_value = mock_job
            dv_result = MagicMock()
            dv_result.scalar_one_or_none.return_value = 3
            img_result = MagicMock()
            img_result.scalar_one_or_none.return_value = "PyTorch"

            db.execute.side_effect = [job_result, dv_result, img_result]

            service = ExperimentService(db)
            result = await service._enrich_experiment(exp)

            assert result["training_job"] is not None
            tj = result["training_job"]
            assert tj["dataset_id"] == dataset_id
            assert tj["dataset_version_id"] == dataset_version_id
            assert tj["image_id"] == image_id
            assert tj["gpu_mode"] == "exclusive"
            assert tj["worker_count"] == 4
            assert tj["priority"] == "high"
            assert tj["mlflow_enabled"] is True
            assert tj["tensorboard_enabled"] is False

    async def test_enrich_job_deleted_returns_none(self):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = None
        with patch("app.services.experiment_service.get_mlflow_client", return_value=mlflow_client):
            db = _mock_db()
            exp = _make_experiment()

            job_result = MagicMock()
            job_result.scalar_one_or_none.return_value = None
            db.execute.return_value = job_result

            service = ExperimentService(db)
            result = await service._enrich_experiment(exp)

            assert result["training_job"] is None


class TestMLflowClient:
    async def test_search_experiments_returns_empty_on_failure(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://nonexistent:5000")
        result = await client.search_experiments()
        assert result == []
        await client.close()

    async def test_get_run_returns_none_on_failure(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://nonexistent:5000")
        result = await client.get_run("nonexistent-run")
        assert result is None
        await client.close()

    async def test_get_or_create_returns_existing(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://nonexistent:5000")
        # search_experiments 失败 → fallback create_experiment → 也失败 → 返回 None
        result = await client.get_or_create_experiment(name="kubeai-test")
        assert result is None
        await client.close()

    async def test_get_or_create_restores_soft_deleted_experiment(self):
        from app.integrations.mlflow.client import MLflowClient

        # 删除后重建同名任务: active 搜不到 → create 撞 RESOURCE_ALREADY_EXISTS(返回 None)
        # → DELETED_ONLY 命中 → restore 复用 id, 并把 kubeai.job_id 重绑到新任务.
        client = MLflowClient(base_url="http://unused:5000")  # 真实 HTTP 不会被调用 (方法全 mock)
        client.search_experiments = AsyncMock(
            side_effect=[
                [],  # ACTIVE_ONLY: 不存在
                [{"experiment_id": "6", "name": "kubeai-8e1be8fa-py312"}],  # DELETED_ONLY: 命中孤儿
            ]
        )
        client.create_experiment = AsyncMock(return_value=None)
        client.restore_experiment = AsyncMock(return_value=True)
        client.set_experiment_tag = AsyncMock(return_value=True)

        result = await client.get_or_create_experiment(
            name="kubeai-8e1be8fa-py312",
            tags={"kubeai.job_id": "new-job-id", "kubeai.tenant_id": "t1"},
        )

        assert result == "6"
        client.create_experiment.assert_awaited_once()
        client.restore_experiment.assert_awaited_once_with("6")
        # 两个 tag 都应重绑到新任务
        assert client.set_experiment_tag.await_count == 2
        rebound = {call.kwargs["key"]: call.kwargs["value"] for call in client.set_experiment_tag.await_args_list}
        assert rebound == {"kubeai.job_id": "new-job-id", "kubeai.tenant_id": "t1"}
        await client.close()

    async def test_get_or_create_returns_none_when_restore_fails(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://unused:5000")
        client.search_experiments = AsyncMock(side_effect=[[], [{"experiment_id": "6"}]])
        client.create_experiment = AsyncMock(return_value=None)
        client.restore_experiment = AsyncMock(return_value=False)  # restore 失败

        result = await client.get_or_create_experiment(name="kubeai-x")

        assert result is None
        await client.close()

    async def test_get_or_create_returns_none_when_no_deleted_match(self):
        from app.integrations.mlflow.client import MLflowClient

        # create 失败但 DELETED_ONLY 也搜不到 (真实错误, 如 MLflow 不可达 / 5xx)
        client = MLflowClient(base_url="http://unused:5000")
        client.search_experiments = AsyncMock(side_effect=[[], []])
        client.create_experiment = AsyncMock(return_value=None)
        client.restore_experiment = AsyncMock(return_value=True)

        result = await client.get_or_create_experiment(name="kubeai-x")

        assert result is None
        client.restore_experiment.assert_not_awaited()  # 没有孤儿可 restore
        await client.close()

    async def test_terminate_run_returns_false_on_failure(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://nonexistent:5000")
        # MLflow 不可达 → runs/update 失败 → 返回 False (best-effort, 不抛错)
        result = await client.terminate_run(run_id="abc")
        assert result is False
        await client.close()

    async def test_create_run_returns_none_on_failure(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://nonexistent:5000")
        # MLflow 不可达 → runs/create 失败 → 返回 None (调用方 fail-fast)
        result = await client.create_run(experiment_id="42")
        assert result is None
        await client.close()

    async def test_delete_experiment_returns_false_on_failure(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://nonexistent:5000")
        result = await client.delete_experiment("42")
        assert result is False
        await client.close()


class TestVcjobBuilderMlflowEnv:
    def test_mlflow_env_injected(self):
        from app.integrations.volcano.job_builder import build_vcjob

        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="abc-123",
            mlflow_tracking_uri="http://mlflow:5000",
            mlflow_experiment_name="kubeai-test-exp",
            mlflow_run_id="run-abc",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        env = {e["name"]: e["value"] for e in container["env"]}
        assert env["MLFLOW_TRACKING_URI"] == "http://mlflow:5000"
        assert env["MLFLOW_EXPERIMENT_NAME"] == "kubeai-test-exp"
        assert env["MLFLOW_RUN_ID"] == "run-abc"

    def test_mlflow_env_not_injected_when_none(self):
        from app.integrations.volcano.job_builder import build_vcjob

        result = build_vcjob(
            vcjob_name="test-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="abc-123",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        env_names = [e["name"] for e in container["env"]]
        assert "MLFLOW_TRACKING_URI" not in env_names
        assert "MLFLOW_EXPERIMENT_NAME" not in env_names
        assert "MLFLOW_RUN_ID" not in env_names


class TestVcjobBuilderTensorboard:
    """验证 TensorBoard sidecar 注入与单 master / 分布式场景的 task name 命名一致性.

    TensorBoard Service 的 selector (``volcano.sh/task-spec=master``) 依赖 task
    name 统一为 ``master``; 如果单 master 时 task 叫别的名字, Service 会找不到
    Pod, TB 链接 502.

    sidecar 以 K8s 原生 sidecar 形式注入 (initContainer + restartPolicy=Always),
    这样 trainer 退出后 Pod 才能进入 Succeeded, GPU 才会释放.
    """

    # build_vcjob 用 job_id 计算 --path_prefix, 必须是可解析的 UUID.
    TB_JOB_ID = "12345678-1234-1234-1234-123456789012"

    def test_single_master_task_named_master(self):
        from app.integrations.volcano.job_builder import build_vcjob

        # worker_count=1 (默认) 也必须叫 "master", 与分布式场景对齐.
        result = build_vcjob(
            vcjob_name="single-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id=self.TB_JOB_ID,
            tensorboard_enabled=True,
        )

        task_names = [t["name"] for t in result["spec"]["tasks"]]
        assert task_names == ["master"], f"单 master 必须只用一个名为 'master' 的 task, 实际 {task_names}"

    def test_distributed_master_named_master(self):
        from app.integrations.volcano.job_builder import build_vcjob

        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id=self.TB_JOB_ID,
            worker_count=4,
            tensorboard_enabled=True,
        )

        task_names = [t["name"] for t in result["spec"]["tasks"]]
        # master 在前, 后续 worker 依次命名
        assert task_names[0] == "master"
        assert task_names[1:] == [f"worker-{i}" for i in range(1, 4)]
        assert task_names.count("master") == 1  # 只有 1 个 master task

    def test_sidecar_is_native_init_container(self):
        """TB 启用 → sidecar 作为原生 sidecar (initContainer + restartPolicy=Always),
        command 注入 per-job --path_prefix; trainer 是唯一主容器且不再声明 6006 端口."""
        from app.integrations.volcano.job_builder import build_vcjob

        result = build_vcjob(
            vcjob_name="single-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id=self.TB_JOB_ID,
            tensorboard_enabled=True,
        )

        spec = result["spec"]["tasks"][0]["template"]["spec"]

        # trainer 是唯一主容器, 不声明 6006 端口 (端口由 sidecar 暴露)
        assert [c["name"] for c in spec["containers"]] == ["trainer"]
        assert "ports" not in spec["containers"][0]

        # sidecar 在 initContainers, restartPolicy=Always → 原生 sidecar
        assert len(spec["initContainers"]) == 1
        sidecar = spec["initContainers"][0]
        assert sidecar["name"] == "tensorboard"
        assert sidecar["restartPolicy"] == "Always"
        assert any(a.startswith("--path_prefix=/tensorboard/") for a in sidecar["command"])

        # trainer 与 sidecar 共享 emptyDir 卷
        assert spec["volumes"][-1] == {"name": "tensorboard-logs", "emptyDir": {}}
        trainer_mounts = [m["name"] for m in spec["containers"][0]["volumeMounts"]]
        assert "tensorboard-logs" in trainer_mounts
        assert [m["name"] for m in sidecar["volumeMounts"]] == ["tensorboard-logs"]

    def test_distributed_worker_strips_sidecar(self):
        """worker task 不应有 sidecar / 共享卷 (避免 Service 路由错配 + 孤儿卷挂载)."""
        from app.integrations.volcano.job_builder import build_vcjob

        result = build_vcjob(
            vcjob_name="dist-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id=self.TB_JOB_ID,
            worker_count=3,
            tensorboard_enabled=True,
        )

        # master task 保留 sidecar (在 initContainers)
        master_spec = result["spec"]["tasks"][0]["template"]["spec"]
        assert "initContainers" in master_spec
        assert master_spec["initContainers"][0]["name"] == "tensorboard"

        # worker task 无 initContainers, 无 tensorboard-logs 卷 / 挂载
        worker_spec = result["spec"]["tasks"][1]["template"]["spec"]
        assert "initContainers" not in worker_spec
        assert "tensorboard-logs" not in [v["name"] for v in worker_spec["volumes"]]
        worker_trainer = worker_spec["containers"][0]
        assert worker_trainer["name"] == "trainer"
        mount_names = [m["name"] for m in worker_trainer.get("volumeMounts", [])]
        assert "tensorboard-logs" not in mount_names

    def test_disabled_omits_sidecar(self):
        """tensorboard_enabled=False → 不注入 sidecar / 端口 / 卷."""
        from app.integrations.volcano.job_builder import build_vcjob

        result = build_vcjob(
            vcjob_name="no-tb-job",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id="abc-123",
            tensorboard_enabled=False,
        )

        spec = result["spec"]["tasks"][0]["template"]["spec"]
        assert [c["name"] for c in spec["containers"]] == ["trainer"]
        assert "ports" not in spec["containers"][0]
        assert "initContainers" not in spec
        assert "tensorboard-logs" not in [v["name"] for v in spec["volumes"]]

    def test_tensorboard_service_selector_matches_master(self):
        """TB Service selector 用 task-spec=master; 必须与 build_vcjob 的 task 名一致."""
        from app.integrations.k8s.tensorboard import build_tensorboard_service
        from app.integrations.volcano.job_builder import build_vcjob

        # 单 master
        single = build_vcjob(
            vcjob_name="svc-match-single",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id=self.TB_JOB_ID,
            tensorboard_enabled=True,
        )
        svc = build_tensorboard_service(uuid.uuid4(), "kubeai-default", "svc-match-single")
        selector = svc.spec.selector

        # Service selector 期望 task-spec=master, 而 build_vcjob 的 task name 也是 master
        single_task_names = [t["name"] for t in single["spec"]["tasks"]]
        assert selector["volcano.sh/task-spec"] == "master"
        assert "master" in single_task_names

        # 分布式: master task 也叫 master, selector 命中正确
        dist = build_vcjob(
            vcjob_name="svc-match-dist",
            namespace="kubeai-default",
            image_ref="pytorch:2.1",
            command="python train.py",
            cpu="4",
            memory="8Gi",
            gpu_count=1,
            gpu_mode="exclusive",
            job_id=self.TB_JOB_ID,
            worker_count=2,
            tensorboard_enabled=True,
        )
        dist_task_names = [t["name"] for t in dist["spec"]["tasks"]]
        assert selector["volcano.sh/task-spec"] == "master"
        assert "master" in dist_task_names
