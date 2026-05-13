import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.experiment import Experiment
from app.services.experiment_service import ExperimentService


def _make_experiment(**overrides):
    defaults = {
        "tenant_id": uuid.uuid4(),
        "training_job_id": uuid.uuid4(),
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
    return db


class TestCreateExperiment:
    @patch("app.services.experiment_service.get_mlflow_client", return_value=None)
    async def test_create_experiment_mlflow_disabled(self, _mock_mlflow):
        db = _mock_db()
        service = ExperimentService(db)
        tenant_id = uuid.uuid4()
        job_id = uuid.uuid4()

        exp = await service.create_experiment(tenant_id=tenant_id, training_job_id=job_id)

        assert exp.tenant_id == tenant_id
        assert exp.training_job_id == job_id
        assert exp.mlflow_experiment_id is None
        assert exp.status == "active"
        db.add.assert_called_once()
        db.flush.assert_awaited_once()

    @patch("app.services.experiment_service.get_mlflow_client")
    async def test_create_experiment_mlflow_enabled_with_experiment(self, mock_get_client):
        mlflow_client = AsyncMock()
        mlflow_client.search_experiments.return_value = [{"experiment_id": "42"}]
        mock_get_client.return_value = mlflow_client

        db = _mock_db()
        service = ExperimentService(db)

        exp = await service.create_experiment(
            tenant_id=uuid.uuid4(),
            training_job_id=uuid.uuid4(),
            mlflow_experiment_name="kubeai-abc-my-job",
        )

        assert exp.mlflow_experiment_id == "42"
        mlflow_client.search_experiments.assert_awaited_once()

    @patch("app.services.experiment_service.get_mlflow_client")
    async def test_create_experiment_mlflow_lookup_fails_gracefully(self, mock_get_client):
        mlflow_client = AsyncMock()
        mlflow_client.search_experiments.side_effect = Exception("connection refused")
        mock_get_client.return_value = mlflow_client

        db = _mock_db()
        service = ExperimentService(db)

        exp = await service.create_experiment(
            tenant_id=uuid.uuid4(),
            training_job_id=uuid.uuid4(),
            mlflow_experiment_name="kubeai-abc-my-job",
        )

        assert exp.mlflow_experiment_id is None
        assert exp.status == "active"


class TestGetExperiments:
    async def test_get_experiments_returns_empty(self):
        db = _mock_db()
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [total_result, list_result]

        service = ExperimentService(db)

        with patch("app.services.experiment_service.get_mlflow_client", return_value=None):
            items, total = await service.get_experiments(tenant_id=uuid.uuid4())

        assert items == []
        assert total == 0

    @patch("app.services.experiment_service.get_mlflow_client", return_value=None)
    async def test_get_experiments_with_dataset_filter(self, _mock_mlflow):
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
        items, total = await service.get_experiments(tenant_id=exp.tenant_id, dataset_id=dataset_id)

        assert total == 1
        assert len(items) == 1

    @patch("app.services.experiment_service.get_mlflow_client", return_value=None)
    async def test_get_experiments_with_date_filter(self, _mock_mlflow):
        db = _mock_db()
        total_result = MagicMock()
        total_result.scalar_one.return_value = 0
        list_result = MagicMock()
        list_result.scalars.return_value.all.return_value = []
        db.execute.side_effect = [total_result, list_result]

        service = ExperimentService(db)
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 12, 31, tzinfo=UTC)
        items, total = await service.get_experiments(
            tenant_id=uuid.uuid4(),
            start_date=start,
            end_date=end,
        )

        assert items == []
        assert total == 0


class TestGetMetricHistory:
    @patch("app.services.experiment_service.get_mlflow_client", return_value=None)
    async def test_get_metric_history_mlflow_disabled(self, _mock_mlflow):
        db = _mock_db()
        exp = _make_experiment(mlflow_experiment_id="mlflow-exp-1")
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

    @patch("app.services.experiment_service.get_mlflow_client")
    async def test_get_metric_history_returns_points(self, mock_get_client):
        mlflow_client = AsyncMock()
        mlflow_client.search_runs.return_value = [
            {"info": {"run_id": "run-abc"}, "data": {"params": [], "metrics": [{"key": "loss", "value": 0.5}]}}
        ]
        mlflow_client.get_metric_history.return_value = [
            {"step": 1, "value": 0.8, "timestamp": 1700000000000},
            {"step": 2, "value": 0.5, "timestamp": 1700000060000},
        ]
        mock_get_client.return_value = mlflow_client

        db = _mock_db()
        exp = _make_experiment(mlflow_experiment_id="mlflow-exp-1")
        result = MagicMock()
        result.scalar_one_or_none.return_value = exp
        db.execute.return_value = result

        service = ExperimentService(db)
        points = await service.get_metric_history(exp.id, exp.tenant_id, "loss")

        assert len(points) == 2
        assert points[0]["step"] == 1
        assert points[0]["value"] == 0.8
        assert points[0]["timestamp"] == 1700000000.0


class TestCompareExperiments:
    @patch("app.services.experiment_service.get_mlflow_client", return_value=None)
    async def test_compare_with_less_than_2_experiments(self, _mock_mlflow):
        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [_make_experiment()]
        db.execute.return_value = result

        service = ExperimentService(db)
        out = await service.compare_experiments(uuid.uuid4(), [uuid.uuid4()])
        assert out is None

    @patch("app.services.experiment_service.get_mlflow_client", return_value=None)
    async def test_compare_with_2_experiments_no_mlflow(self, _mock_mlflow):
        tenant_id = uuid.uuid4()
        exp1 = _make_experiment(tenant_id=tenant_id)
        exp2 = _make_experiment(tenant_id=tenant_id)

        db = _mock_db()
        exp_result = MagicMock()
        exp_result.scalars.return_value.all.return_value = [exp1, exp2]
        job_result = MagicMock()
        job_result.scalars.return_value.all.return_value = []
        dv_result = MagicMock()
        dv_result.all.return_value = []
        img_result = MagicMock()
        img_result.all.return_value = []
        hp_job_result = MagicMock()
        hp_job_result.scalars.return_value.all.return_value = []

        db.execute.side_effect = [exp_result, job_result, hp_job_result]

        service = ExperimentService(db)
        out = await service.compare_experiments(tenant_id, [exp1.id, exp2.id])

        assert out is not None
        assert len(out["experiments"]) == 2
        assert out["hyperparams_diff"] == []
        assert out["metrics_comparison"] == []

    @patch("app.services.experiment_service.get_mlflow_client")
    async def test_compare_with_hyperparams_diff(self, mock_get_client):
        mock_get_client.return_value = None

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

        service = ExperimentService(db)
        out = await service.compare_experiments(tenant_id, [exp1.id, exp2.id])

        assert out is not None
        diff_map = {d["key"]: d for d in out["hyperparams_diff"]}
        assert diff_map["lr"]["is_different"] is True
        assert diff_map["epochs"]["is_different"] is False
        assert diff_map["batch_size"]["is_different"] is False


class TestSyncExperimentStatus:
    async def test_sync_to_completed(self):
        exp = _make_experiment(status="active")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        service = ExperimentService(db)

        with patch("app.services.experiment_service.get_mlflow_client", return_value=None):
            await service.sync_experiment_status(exp.training_job_id, "succeeded")

        assert exp.status == "completed"

    async def test_sync_to_failed(self):
        exp = _make_experiment(status="active")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        service = ExperimentService(db)

        with patch("app.services.experiment_service.get_mlflow_client", return_value=None):
            await service.sync_experiment_status(exp.training_job_id, "failed")

        assert exp.status == "failed"

    async def test_sync_no_experiments(self):
        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        service = ExperimentService(db)

        with patch("app.services.experiment_service.get_mlflow_client", return_value=None):
            await service.sync_experiment_status(uuid.uuid4(), "succeeded")

    async def test_sync_running_job_ignored(self):
        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        service = ExperimentService(db)

        with patch("app.services.experiment_service.get_mlflow_client", return_value=None):
            await service.sync_experiment_status(uuid.uuid4(), "running")

    @patch("app.services.experiment_service.get_mlflow_client")
    async def test_sync_with_mlflow_run_status(self, mock_get_client):
        mlflow_client = AsyncMock()
        mlflow_client.get_run.return_value = {
            "info": {"status": "FINISHED", "run_id": "abc"},
        }
        mock_get_client.return_value = mlflow_client

        exp = _make_experiment(status="active", mlflow_run_id="abc")

        db = _mock_db()
        result = MagicMock()
        result.scalars.return_value.all.return_value = [exp]
        db.execute.return_value = result

        service = ExperimentService(db)
        await service.sync_experiment_status(exp.training_job_id, "succeeded")

        assert exp.status == "completed"


class TestEnrichExperimentNewFields:
    @patch("app.services.experiment_service.get_mlflow_client", return_value=None)
    async def test_enrich_includes_new_uuid_fields(self, _mock_mlflow):
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
        mock_job.metrics_port = 6006
        mock_job.started_at = None

        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = mock_job
        dv_result = MagicMock()
        dv_result.scalar_one_or_none.return_value = 3
        img_result = MagicMock()
        img_result.scalar_one_or_none.return_value = "PyTorch"

        db.execute.side_effect = [job_result, dv_result, img_result]

        service = ExperimentService(db)
        result = await service._enrich_experiment(exp, None)

        assert result["training_job"] is not None
        tj = result["training_job"]
        assert tj["dataset_id"] == dataset_id
        assert tj["dataset_version_id"] == dataset_version_id
        assert tj["image_id"] == image_id
        assert tj["gpu_mode"] == "exclusive"
        assert tj["worker_count"] == 4
        assert tj["priority"] == "high"
        assert tj["metrics_port"] == 6006

    @patch("app.services.experiment_service.get_mlflow_client", return_value=None)
    async def test_enrich_job_deleted_returns_none(self, _mock_mlflow):
        db = _mock_db()
        exp = _make_experiment()

        job_result = MagicMock()
        job_result.scalar_one_or_none.return_value = None
        db.execute.return_value = job_result

        service = ExperimentService(db)
        result = await service._enrich_experiment(exp, None)

        assert result["training_job"] is None


class TestMLflowClientDegradation:
    async def test_get_mlflow_client_disabled(self):
        with patch("app.integrations.mlflow.client.settings") as mock_settings:
            mock_settings.MLFLOW_ENABLED = False
            from app.integrations.mlflow.client import get_mlflow_client

            assert get_mlflow_client() is None

    async def test_get_mlflow_client_enabled(self):
        with patch("app.integrations.mlflow.client.settings") as mock_settings:
            mock_settings.MLFLOW_ENABLED = True
            mock_settings.MLFLOW_TRACKING_URI = "http://mlflow:5000"
            from app.integrations.mlflow.client import get_mlflow_client

            client = get_mlflow_client()
            assert client is not None
            assert client._base_url == "http://mlflow:5000"

    async def test_search_experiments_returns_empty_on_failure(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://nonexistent:5000")
        result = await client.search_experiments()
        assert result == []

    async def test_get_run_returns_none_on_failure(self):
        from app.integrations.mlflow.client import MLflowClient

        client = MLflowClient(base_url="http://nonexistent:5000")
        result = await client.get_run("nonexistent-run")
        assert result is None


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
            mlflow_run_name="job-abc12345",
        )

        container = result["spec"]["tasks"][0]["template"]["spec"]["containers"][0]
        env = {e["name"]: e["value"] for e in container["env"]}
        assert env["MLFLOW_TRACKING_URI"] == "http://mlflow:5000"
        assert env["MLFLOW_EXPERIMENT_NAME"] == "kubeai-test-exp"
        assert env["MLFLOW_RUN_NAME"] == "job-abc12345"

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
        assert "MLFLOW_RUN_NAME" not in env_names
