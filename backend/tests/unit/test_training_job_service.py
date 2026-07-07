import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kubernetes_asyncio.client.exceptions import ApiException

from app.core.exceptions import ExternalServiceException, QuotaExceededException
from app.integrations.k8s.pod import map_failure_message
from app.models.enums import TrainingJobStatus
from app.models.image import Image
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
from app.models.user import User
from app.services.training_job_service import TrainingJobService

_NOW = datetime(2026, 5, 8, 12, 0, 0, tzinfo=UTC)


def _sync_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _make_tenant(**overrides):
    defaults = {
        "name": "default-tenant",
        "display_name": "Default",
        "k8s_namespace_name": "kubeai-default",
        "gpu_limit": 10,
    }
    defaults.update(overrides)
    t = Tenant(**defaults)
    t.id = uuid.uuid4()
    t.created_at = _NOW
    t.updated_at = _NOW
    return t


def _make_image(**overrides):
    defaults = {
        "name": "PyTorch 2.1",
        "tag": "2.1.0-cuda12.1",
        "image_ref": "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
        "source": "preset",
        "is_enabled": True,
        "category": "training",
    }
    defaults.update(overrides)
    img = Image(**defaults)
    img.id = uuid.uuid4()
    img.created_at = _NOW
    img.updated_at = _NOW
    img.deleted_at = None
    return img


def _make_user(**overrides):
    defaults = {
        "username": "testuser",
        "email": "test@example.com",
        "hashed_password": "hash",
        "auth_provider": "local",
        "external_id": "testuser",
    }
    defaults.update(overrides)
    u = User(**defaults)
    u.id = uuid.uuid4()
    u.created_at = _NOW
    u.updated_at = _NOW
    u.deleted_at = None
    return u


def _make_job(**overrides):
    defaults = {
        "tenant_id": uuid.uuid4(),
        "name": "test-job",
        "created_by": uuid.uuid4(),
        "image_id": uuid.uuid4(),
        "command": "python train.py",
        "gpu_count": 1,
        "gpu_mode": "exclusive",
        "cpu": "4",
        "memory": "8Gi",
        "priority": "normal",
        "worker_count": 1,
        "mlflow_enabled": False,
        "status": TrainingJobStatus.PENDING,
    }
    defaults.update(overrides)
    job = TrainingJob(**defaults)
    job.id = uuid.uuid4()
    job.created_at = _NOW
    job.updated_at = _NOW
    return job


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return TrainingJobService(mock_db)


class TestCreateTrainingJobQuotaCheck:
    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used")
    async def test_single_job_gpu_quota(self, mock_quota, mock_build, mock_create, service, mock_db):
        tenant = _make_tenant(gpu_limit=10)
        image = _make_image()
        user = _make_user()
        mock_quota.return_value = {"requests.nvidia.com/gpu": "3"}
        mock_build.return_value = {"metadata": {"name": "test"}}

        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="test-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=2,
            worker_count=1,
        )
        assert job.status == TrainingJobStatus.PENDING

        # Reset execute mock for execute phase
        mock_db.execute.side_effect = [
            _sync_result(job),
            _sync_result(tenant),
            _sync_result(user),
            _sync_result(image),
        ]
        await service.execute_training_job_submission(job.id, tenant.id)
        mock_create.assert_called_once()

    @patch("app.services.training_job_service.get_quota_used")
    async def test_distributed_gpu_quota_total(self, mock_quota, service, mock_db):
        tenant = _make_tenant(gpu_limit=10)
        image = _make_image()
        user = _make_user()
        mock_quota.return_value = {"requests.nvidia.com/gpu": "8"}

        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="dist-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=2,
            worker_count=4,
        )

        mock_db.execute.side_effect = [
            _sync_result(job),
            _sync_result(tenant),
            _sync_result(user),
            _sync_result(image),
        ]
        with pytest.raises(QuotaExceededException):
            await service.execute_training_job_submission(job.id, tenant.id)

    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used")
    async def test_distributed_quota_passes(self, mock_quota, mock_build, mock_create, service, mock_db):
        tenant = _make_tenant(gpu_limit=20)
        image = _make_image()
        user = _make_user()
        mock_quota.return_value = {"requests.nvidia.com/gpu": "0"}
        mock_build.return_value = {"metadata": {"name": "test"}}

        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="dist-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=2,
            worker_count=4,
        )

        mock_db.execute.side_effect = [
            _sync_result(job),
            _sync_result(tenant),
            _sync_result(user),
            _sync_result(image),
        ]
        await service.execute_training_job_submission(job.id, tenant.id)
        mock_create.assert_called_once()

    async def test_zero_gpu_skips_quota(self, service, mock_db):
        tenant = _make_tenant(gpu_limit=0)
        image = _make_image()
        user = _make_user()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="cpu-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=0,
            worker_count=1,
        )
        assert job.status == TrainingJobStatus.PENDING

        # No quota check needed for 0 GPU - just verify submission works
        mock_db.execute.side_effect = [
            _sync_result(job),
            _sync_result(tenant),
            _sync_result(user),
            _sync_result(image),
        ]
        with (
            patch("app.services.training_job_service.create_vcjob"),
            patch("app.services.training_job_service.build_vcjob"),
        ):
            await service.execute_training_job_submission(job.id, tenant.id)


class TestCreateTrainingJobWorkerCount:
    async def test_worker_count_saved_to_db(self, service, mock_db):
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="dist-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=1,
            worker_count=4,
        )

        assert job.worker_count == 4

    async def test_worker_count_passed_to_builder(self, mock_db):
        """worker_count is a DB-only attribute in create_training_job_record, verified via saved job."""
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]

        job = await TrainingJobService(mock_db).create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="dist-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=1,
            worker_count=8,
        )

        assert job.worker_count == 8


class TestStopTrainingJob:
    async def test_stop_distributed_job(self, service, mock_db):
        job = _make_job(
            status=TrainingJobStatus.RUNNING,
            vcjob_name="training-dist-job",
            worker_count=4,
        )
        mock_db.execute.return_value = _sync_result(job)

        result = await service.stop_training_job_record(job.id, job.tenant_id)

        assert result.status == TrainingJobStatus.STOPPED


class TestDeleteJobMlflowCleanup:
    """删除训练任务时一并删除 MLflow experiment (连带 run), 避免孤儿 MLflow 数据."""

    @patch("app.services.training_job_service.delete_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_execute_delete_cleans_mlflow(self, mock_exp_cls, mock_delete, service, mock_db):
        mock_exp_cls.return_value.delete_experiment = AsyncMock()

        await service.execute_training_job_delete(
            uuid.uuid4(),
            "training-x",
            "kubeai-default",
            tensorboard_enabled=False,
            mlflow_experiment_id="exp-42",
        )

        mock_exp_cls.return_value.delete_experiment.assert_awaited_once_with("exp-42")
        mock_delete.assert_awaited_once()  # VCJob 仍被删除

    @patch("app.services.training_job_service.delete_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_execute_delete_skips_mlflow_when_no_experiment(self, mock_exp_cls, mock_delete, service, mock_db):
        await service.execute_training_job_delete(
            uuid.uuid4(),
            "training-x",
            "kubeai-default",
            tensorboard_enabled=False,
            mlflow_experiment_id=None,
        )

        mock_exp_cls.return_value.delete_experiment.assert_not_called()

    async def test_delete_record_returns_mlflow_experiment_id(self, service, mock_db):
        """delete_training_job_record 须在 cascade 删除 Experiment 前带出 mlflow_experiment_id."""
        job = _make_job(status=TrainingJobStatus.SUCCEEDED, vcjob_name="training-x", tensorboard_enabled=False)
        tenant = _make_tenant()
        exp_result = MagicMock()
        exp_result.scalar_one_or_none.return_value = "exp-99"
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant), exp_result]

        result = await service.delete_training_job_record(job.id, job.tenant_id)

        assert result == ("training-x", "kubeai-default", False, "exp-99")


class TestStopJobMlflowTermination:
    """P0 回归: 停止任务时主动 KILL MLflow run, 避免留下永远 RUNNING 的僵尸 run.

    Pod 被 SIGTERM 强杀时脚本来不及 end_run, 若平台不主动终止, MLflow run 永远停在 RUNNING,
    且会把后续 sync 的 experiment 状态锁死在 active.
    """

    @patch("app.services.training_job_service.delete_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_stop_terminates_mlflow_when_enabled(self, mock_exp_cls, mock_delete, service, mock_db):
        tenant = _make_tenant()
        job = _make_job(mlflow_enabled=True, vcjob_name="training-x")
        mock_exp_cls.return_value.terminate_experiments_for_job = AsyncMock()
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]

        await service.execute_training_job_stop(job.id, tenant.id)

        mock_exp_cls.return_value.terminate_experiments_for_job.assert_awaited_once_with(job.id)
        mock_delete.assert_awaited_once()  # VCJob 仍被删除

    @patch("app.services.training_job_service.delete_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_stop_skips_terminate_when_mlflow_disabled(self, mock_exp_cls, mock_delete, service, mock_db):
        tenant = _make_tenant()
        job = _make_job(mlflow_enabled=False, vcjob_name="training-x")
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]

        await service.execute_training_job_stop(job.id, tenant.id)

        mock_exp_cls.return_value.terminate_experiments_for_job.assert_not_called()
        mock_delete.assert_awaited_once()

    @patch("app.services.training_job_service.delete_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_stop_terminate_failure_does_not_block_vcjob_delete(
        self, mock_exp_cls, mock_delete, service, mock_db
    ):
        """MLflow 终止失败 (best-effort) → 不影响 VCJob 删除."""
        tenant = _make_tenant()
        job = _make_job(mlflow_enabled=True, vcjob_name="training-x")
        mock_exp_cls.return_value.terminate_experiments_for_job = AsyncMock(side_effect=RuntimeError("MLflow down"))
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]

        await service.execute_training_job_stop(job.id, tenant.id)  # 不应抛错

        mock_delete.assert_awaited_once()


class TestStreamLogs:
    @patch("app.services.training_job_service.stream_pod_logs")
    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_stream_logs_finds_default_pod(self, mock_list_pods, mock_stream, service, mock_db):
        job = _make_job(status=TrainingJobStatus.RUNNING, vcjob_name="training-test-job")
        tenant = _make_tenant()
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]
        mock_list_pods.return_value = [
            {"pod_name": "training-test-job-master-0", "role": "master", "status": "running"}
        ]

        async def fake_stream(*a, **kw):
            yield "line1"
            yield "line2"

        mock_stream.side_effect = fake_stream

        lines = []
        async for line in service.stream_logs(job_id=job.id, tenant_id=job.tenant_id):
            lines.append(line)

        assert lines == ["line1", "line2"]

    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_stream_logs_no_vcjob(self, mock_list_pods, service, mock_db):
        from app.core.exceptions import BadRequestException

        job = _make_job(status=TrainingJobStatus.PENDING, vcjob_name=None)
        mock_db.execute.return_value = _sync_result(job)

        with pytest.raises(BadRequestException, match="尚未提交"):
            async for _ in service.stream_logs(job_id=job.id, tenant_id=job.tenant_id):
                pass

    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_stream_logs_no_pods(self, mock_list_pods, service, mock_db):
        from app.core.exceptions import NotFoundException

        job = _make_job(status=TrainingJobStatus.RUNNING, vcjob_name="training-test-job")
        tenant = _make_tenant()
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]
        mock_list_pods.return_value = []

        with pytest.raises(NotFoundException, match="Pod"):
            async for _ in service.stream_logs(job_id=job.id, tenant_id=job.tenant_id):
                pass


class TestGetLogs:
    @patch("app.services.training_job_service.get_pod_log")
    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_get_logs_returns_lines(self, mock_list_pods, mock_get_log, service, mock_db):
        job = _make_job(status=TrainingJobStatus.SUCCEEDED, vcjob_name="training-test-job")
        tenant = _make_tenant()
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]
        mock_list_pods.return_value = [
            {"pod_name": "training-test-job-master-0", "role": "master", "status": "succeeded"}
        ]
        mock_get_log.return_value = "line1\nline2\nline3"

        lines, has_more, total = await service.get_logs(job_id=job.id, tenant_id=job.tenant_id)

        assert lines == ["line1", "line2", "line3"]
        assert has_more is False
        assert total == 3

    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_get_logs_no_vcjob(self, mock_list_pods, service, mock_db):
        job = _make_job(status=TrainingJobStatus.PENDING, vcjob_name=None)
        mock_db.execute.return_value = _sync_result(job)

        from app.core.exceptions import BadRequestException

        with pytest.raises(BadRequestException, match="尚未提交"):
            await service.get_logs(job_id=job.id, tenant_id=job.tenant_id)

    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_get_logs_no_pods(self, mock_list_pods, service, mock_db):
        job = _make_job(status=TrainingJobStatus.SUCCEEDED, vcjob_name="training-test-job")
        tenant = _make_tenant()
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]
        mock_list_pods.return_value = []

        lines, has_more, total = await service.get_logs(job_id=job.id, tenant_id=job.tenant_id)

        assert lines == []
        assert has_more is False
        assert total == 0


class TestListPods:
    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_list_pods(self, mock_list_vcjob_pods, service, mock_db):
        job = _make_job(status=TrainingJobStatus.RUNNING, vcjob_name="training-test-job")
        tenant = _make_tenant()
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]
        mock_list_vcjob_pods.return_value = [
            {"pod_name": "training-test-job-master-0", "role": "master", "status": "running"},
            {"pod_name": "training-test-job-worker-0", "role": "worker-0", "status": "running"},
        ]

        result = await service.list_pods(job_id=job.id, tenant_id=job.tenant_id)

        assert len(result) == 2
        assert result[0]["role"] == "master"

    async def test_list_pods_no_vcjob(self, service, mock_db):
        job = _make_job(status=TrainingJobStatus.PENDING, vcjob_name=None)
        mock_db.execute.return_value = _sync_result(job)

        result = await service.list_pods(job_id=job.id, tenant_id=job.tenant_id)

        assert result == []


class TestMapFailureMessage:
    def test_oom_killed(self):
        msg = map_failure_message({"exit_code": 137, "reason": "OOMKilled", "message": ""})
        assert "OOM" in msg
        assert "内存" in msg

    def test_exit_code_137(self):
        msg = map_failure_message({"exit_code": 137, "reason": "Error", "message": ""})
        assert "SIGKILL" in msg

    def test_image_pull_backoff(self):
        msg = map_failure_message({"exit_code": 0, "reason": "ImagePullBackOff", "message": ""})
        assert "镜像拉取失败" in msg

    def test_err_image_pull(self):
        msg = map_failure_message({"exit_code": 0, "reason": "ErrImagePull", "message": ""})
        assert "镜像拉取失败" in msg

    def test_container_cannot_run(self):
        msg = map_failure_message({"exit_code": 1, "reason": "ContainerCannotRun", "message": ""})
        assert "容器启动失败" in msg

    def test_exit_code_1(self):
        msg = map_failure_message({"exit_code": 1, "reason": "Error", "message": ""})
        assert "训练脚本执行错误" in msg

    def test_other_exit_code(self):
        msg = map_failure_message({"exit_code": 42, "reason": "Error", "message": ""})
        assert "退出码: 42" in msg

    def test_zero_exit_code_with_reason(self):
        msg = map_failure_message({"exit_code": 0, "reason": "Unknown", "message": ""})
        assert "失败" in msg


class TestExtractFailureReason:
    # _extract_failure_reason 现在委托给 pod.resolve_pod_failure_reason, 后者使用
    # pod 模块自身的 list_vcjob_pods / get_pod_failure_info, 因此 patch 目标是 pod 模块.
    @patch("app.integrations.k8s.pod.get_pod_failure_info")
    @patch("app.integrations.k8s.pod.list_vcjob_pods")
    async def test_oom_failure(self, mock_list_pods, mock_failure_info, service):
        mock_list_pods.return_value = [{"pod_name": "pod-1", "role": "master", "status": "failed"}]
        mock_failure_info.return_value = {
            "exit_code": 137,
            "reason": "OOMKilled",
            "message": "",
            "signal": None,
            "finished_at": None,
        }

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "OOM" in result

    @patch("app.integrations.k8s.pod.get_pod_failure_info")
    @patch("app.integrations.k8s.pod.list_vcjob_pods")
    async def test_image_pull_failure(self, mock_list_pods, mock_failure_info, service):
        mock_list_pods.return_value = [{"pod_name": "pod-1", "role": "master", "status": "pending"}]
        mock_failure_info.return_value = {
            "exit_code": 0,
            "reason": "ImagePullBackOff",
            "message": "",
            "signal": None,
            "finished_at": None,
        }

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "镜像拉取失败" in result

    @patch("app.integrations.k8s.pod.get_pod_failure_info")
    @patch("app.integrations.k8s.pod.list_vcjob_pods")
    async def test_no_failure_info(self, mock_list_pods, mock_failure_info, service):
        mock_list_pods.return_value = [{"pod_name": "pod-1", "role": "master", "status": "failed"}]
        mock_failure_info.return_value = None

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "未能获取具体失败原因" in result

    @patch("app.integrations.k8s.pod.list_vcjob_pods")
    async def test_no_pods(self, mock_list_pods, service):
        mock_list_pods.return_value = []

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "已被清理" in result

    @patch("app.integrations.k8s.pod.list_vcjob_pods")
    async def test_list_pods_exception(self, mock_list_pods, service):
        mock_list_pods.side_effect = Exception("K8s error")

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "不可用" in result

    @patch("app.integrations.k8s.pod.get_pod_failure_info")
    @patch("app.integrations.k8s.pod.list_vcjob_pods")
    async def test_multiple_pods_first_has_reason(self, mock_list_pods, mock_failure_info, service):
        mock_list_pods.return_value = [
            {"pod_name": "pod-master", "role": "master", "status": "failed"},
            {"pod_name": "pod-worker-0", "role": "worker-0", "status": "failed"},
        ]
        mock_failure_info.side_effect = [
            {"exit_code": 137, "reason": "OOMKilled", "message": "", "signal": None, "finished_at": None},
            {"exit_code": 1, "reason": "Error", "message": "", "signal": None, "finished_at": None},
        ]

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "OOM" in result
        assert mock_failure_info.call_count == 1


class TestSyncJobStatusWithFailureReason:
    @patch("app.services.training_job_service.TrainingJobService._extract_failure_reason", new_callable=AsyncMock)
    @patch("app.services.training_job_service.batch_get_vcjob_phases")
    async def test_failed_status_extracts_reason(self, mock_phases, mock_extract, service, mock_db):
        job = _make_job(status=TrainingJobStatus.RUNNING, vcjob_name="training-test-job")
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_phases.return_value = {"training-test-job": "failed"}
        mock_extract.return_value = "内存不足 (OOM)：训练容器因超出内存限制被终止。"  # noqa: RUF001

        await service._sync_job_status(job)

        assert job.status == TrainingJobStatus.FAILED
        assert "OOM" in job.error_message

    @patch("app.services.training_job_service.batch_get_vcjob_phases")
    async def test_succeeded_status_no_error_message(self, mock_phases, service, mock_db):
        job = _make_job(status=TrainingJobStatus.RUNNING, vcjob_name="training-test-job")
        tenant = _make_tenant()
        mock_db.execute.return_value = _sync_result(tenant)
        mock_phases.return_value = {"training-test-job": "succeeded"}

        await service._sync_job_status(job)

        assert job.status == TrainingJobStatus.SUCCEEDED
        assert job.error_message is None


class TestRetryTrainingJob:
    async def test_retry_failed_job(self, service, mock_db):
        original_job = _make_job(status=TrainingJobStatus.FAILED, vcjob_name="training-test-job")
        original_job.hyperparameters = {"lr": "0.001", "epochs": "10"}
        original_job.description = "测试任务"
        original_job.tensorboard_enabled = True
        tenant = _make_tenant(id=original_job.tenant_id)
        image = _make_image(id=original_job.image_id)

        mock_db.execute.side_effect = [
            _sync_result(original_job),  # _get_job_or_fail
            _sync_result(tenant),  # _get_tenant_or_fail (清理旧 VCJob)
            _sync_result(image),  # _get_image_or_fail (创建新任务)
        ]

        result = await service.retry_training_job(original_job.id, original_job.tenant_id, uuid.uuid4())

        assert "retry-" in result.name
        assert result.name.startswith(original_job.name)
        assert result.status == TrainingJobStatus.PENDING
        assert result.worker_count == original_job.worker_count

    async def test_retry_running_job_raises(self, service, mock_db):
        job = _make_job(status=TrainingJobStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(job)

        with pytest.raises(Exception, match="仅失败或已停止"):
            await service.retry_training_job(job.id, job.tenant_id, uuid.uuid4())

    async def test_retry_succeeded_job_raises(self, service, mock_db):
        job = _make_job(status=TrainingJobStatus.SUCCEEDED)
        mock_db.execute.return_value = _sync_result(job)

        with pytest.raises(Exception, match="仅失败或已停止"):
            await service.retry_training_job(job.id, job.tenant_id, uuid.uuid4())


class TestCreateTrainingJobWithSourceExperiment:
    async def test_source_experiment_id_appended_to_description(self, service, mock_db):
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]
        source_exp_id = uuid.uuid4()

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="reproduce-job",
            image_id=image.id,
            command="python train.py",
            source_experiment_id=source_exp_id,
        )

        assert f"基于实验 #{source_exp_id} 复现" in job.description

    async def test_source_experiment_id_appends_to_existing_description(self, service, mock_db):
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]
        source_exp_id = uuid.uuid4()

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="reproduce-job",
            description="原始描述",
            image_id=image.id,
            command="python train.py",
            source_experiment_id=source_exp_id,
        )

        assert job.description == f"原始描述（基于实验 #{source_exp_id} 复现）"  # noqa: RUF001

    async def test_no_source_experiment_id_keeps_description(self, service, mock_db):
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="normal-job",
            description="普通任务",
            image_id=image.id,
            command="python train.py",
        )

        assert job.description == "普通任务"


class TestSourceFieldDefaults:
    async def test_manual_source_by_default(self, service, mock_db):
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="manual-job",
            image_id=image.id,
            command="python train.py",
        )

        assert job.source == "manual"
        assert job.source_env_id is None

    async def test_experiment_reproduction_source(self, service, mock_db):
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant), _sync_result(user)]
        source_exp_id = uuid.uuid4()

        job = await service.create_training_job_record(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="reproduce-job",
            image_id=image.id,
            command="python train.py",
            source_experiment_id=source_exp_id,
        )

        assert job.source == "experiment_reproduction"
        assert f"基于实验 #{source_exp_id} 复现" in job.description


class TestMlflowPerJobBinding:
    @patch("app.services.training_job_service.create_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.build_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.get_quota_used", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_execute_creates_experiment_when_enabled(
        self, mock_exp_service_cls, mock_quota, mock_build, mock_create, service, mock_db
    ):
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        job = _make_job(mlflow_enabled=True)

        mock_quota.return_value = {}
        mock_build.return_value = {"metadata": {"name": "test"}}
        mock_create.return_value = None

        mock_db.execute.side_effect = [
            _sync_result(job),
            _sync_result(tenant),
            _sync_result(user),
            _sync_result(image),
        ]

        # experiment_service.create_experiment 应当被调用 1 次, 返回带 run_id 的 experiment
        mock_experiment = MagicMock()
        mock_experiment.mlflow_run_id = "run-xyz"
        mock_exp_service_cls.return_value.create_experiment = AsyncMock(return_value=mock_experiment)

        await service.execute_training_job_submission(job.id, tenant.id)

        mock_exp_service_cls.return_value.create_experiment.assert_awaited_once()
        kwargs = mock_exp_service_cls.return_value.create_experiment.await_args.kwargs
        assert kwargs["tenant_id"] == tenant.id
        assert kwargs["training_job_id"] == job.id
        assert kwargs["mlflow_experiment_name"].startswith("kubeai-")
        # 预创建的 run_id 应注入 build_vcjob (强绑定)
        assert mock_build.call_args.kwargs["mlflow_run_id"] == "run-xyz"

    @patch("app.services.training_job_service.create_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_execute_skips_mlflow_by_default(
        self, mock_exp_service_cls, mock_quota, mock_build, mock_create, service, mock_db
    ):
        # 默认 mlflow_enabled=False → 不创建 Experiment 记录
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        job = _make_job()  # 不传 mlflow_enabled, 默认 False

        mock_quota.return_value = {}
        mock_build.return_value = {"metadata": {"name": "test"}}
        mock_create.return_value = None

        mock_db.execute.side_effect = [
            _sync_result(job),
            _sync_result(tenant),
            _sync_result(user),
            _sync_result(image),
        ]

        await service.execute_training_job_submission(job.id, tenant.id)

        mock_exp_service_cls.return_value.create_experiment.assert_not_called()
        # build_vcjob 收到的 mlflow_* 参数应全为 None
        build_kwargs = mock_build.call_args.kwargs
        assert build_kwargs["mlflow_tracking_uri"] is None
        assert build_kwargs["mlflow_experiment_name"] is None

    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_execute_fails_fast_when_mlflow_unavailable(
        self, mock_exp_service_cls, mock_quota, mock_build, service, mock_db
    ):
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        job = _make_job(mlflow_enabled=True)

        mock_quota.return_value = {}
        # ExperimentService.create_experiment 抛 RuntimeError (MLflow 不可用)
        mock_exp_service_cls.return_value.create_experiment = AsyncMock(
            side_effect=RuntimeError("无法创建 MLflow experiment: kubeai-x")
        )

        mock_db.execute.side_effect = [
            _sync_result(job),
            _sync_result(tenant),
            _sync_result(user),
            _sync_result(image),
        ]

        with pytest.raises(RuntimeError, match="MLflow"):
            await service.execute_training_job_submission(job.id, tenant.id)

        # MLflow 不可用 → build_vcjob 都不会被调用 → VCJob 不提交
        mock_build.assert_not_called()
        assert job.status == TrainingJobStatus.PENDING  # 状态未变

    @patch("app.services.training_job_service.create_vcjob", new_callable=AsyncMock)
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used", new_callable=AsyncMock)
    @patch("app.services.training_job_service.ExperimentService")
    async def test_submission_maps_crd_missing_404_to_external_service_exception(
        self, mock_exp_service_cls, mock_quota, mock_build, mock_create, service, mock_db
    ):
        """集群未装 Volcano VCJob CRD → create_vcjob 抛 ApiException 404 → 友好 ExternalServiceException.

        同时验证: 失败分支仍 commit 已 flush 的 Experiment (重试幂等短路依赖其持久化),
        而非回滚 (回滚会导致重试重复创建 MLflow run).
        """
        tenant = _make_tenant()
        image = _make_image()
        user = _make_user()
        job = _make_job(mlflow_enabled=True)

        mock_quota.return_value = {}
        mock_build.return_value = {"metadata": {"name": "test"}}
        mock_create.side_effect = ApiException(status=404, reason="the server could not find the requested resource")

        mock_experiment = MagicMock()
        mock_experiment.mlflow_run_id = "run-xyz"
        mock_exp_service_cls.return_value.create_experiment = AsyncMock(return_value=mock_experiment)

        mock_db.execute.side_effect = [
            _sync_result(job),
            _sync_result(tenant),
            _sync_result(user),
            _sync_result(image),
        ]

        with pytest.raises(ExternalServiceException, match="Volcano VCJob CRD 未安装"):
            await service.execute_training_job_submission(job.id, tenant.id)

        # 失败分支持久化已 flush 的 Experiment, 供重试幂等短路 (而非 rollback).
        mock_db.commit.assert_awaited()

    async def test_create_training_job_record_default_mlflow_disabled(self, service, mock_db):
        image = _make_image()
        mock_db.execute.side_effect = [_sync_result(image)]

        # 不传 mlflow_enabled, 默认值应为 False
        job = await service.create_training_job_record(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="test-default-no-mlflow",
            image_id=image.id,
            command="python train.py",
        )
        assert job.mlflow_enabled is False

    async def test_create_training_job_record_explicit_true(self, service, mock_db):
        image = _make_image()
        mock_db.execute.side_effect = [_sync_result(image)]

        job = await service.create_training_job_record(
            tenant_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            name="test-with-mlflow",
            image_id=image.id,
            command="python train.py",
            mlflow_enabled=True,
        )
        assert job.mlflow_enabled is True
