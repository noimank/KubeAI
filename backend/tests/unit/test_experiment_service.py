import uuid
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
