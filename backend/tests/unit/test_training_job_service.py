import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import QuotaExceededException
from app.models.enums import TrainingJobStatus
from app.models.image import Image
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob
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
    }
    defaults.update(overrides)
    img = Image(**defaults)
    img.id = uuid.uuid4()
    img.created_at = _NOW
    img.updated_at = _NOW
    img.deleted_at = None
    return img


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
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return TrainingJobService(mock_db)


class TestCreateTrainingJobQuotaCheck:
    @patch("app.services.training_job_service.get_quota_used")
    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    async def test_single_job_gpu_quota(self, mock_build, mock_create, mock_quota, service, mock_db):
        tenant = _make_tenant(gpu_limit=10)
        image = _make_image()
        mock_quota.return_value = {"requests.nvidia.com/gpu": "3"}

        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant)]

        await service.create_training_job(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="test-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=2,
            worker_count=1,
        )

        mock_create.assert_called_once()

    @patch("app.services.training_job_service.get_quota_used")
    async def test_distributed_gpu_quota_total(self, mock_quota, service, mock_db):
        tenant = _make_tenant(gpu_limit=10)
        image = _make_image()
        mock_quota.return_value = {"requests.nvidia.com/gpu": "8"}

        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant)]

        with pytest.raises(QuotaExceededException):
            await service.create_training_job(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                name="dist-job",
                image_id=image.id,
                command="python train.py",
                gpu_count=2,
                worker_count=4,
            )

    @patch("app.services.training_job_service.get_quota_used")
    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    async def test_distributed_quota_passes(self, mock_build, mock_create, mock_quota, service, mock_db):
        tenant = _make_tenant(gpu_limit=20)
        image = _make_image()
        mock_quota.return_value = {"requests.nvidia.com/gpu": "0"}

        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant)]

        await service.create_training_job(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="dist-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=2,
            worker_count=4,
        )

        mock_create.assert_called_once()

    async def test_zero_gpu_skips_quota(self, service, mock_db):
        tenant = _make_tenant(gpu_limit=0)
        image = _make_image()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant)]

        with (
            patch("app.services.training_job_service.create_vcjob"),
            patch("app.services.training_job_service.build_vcjob"),
        ):
            await service.create_training_job(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                name="cpu-job",
                image_id=image.id,
                command="python train.py",
                gpu_count=0,
                worker_count=1,
            )


class TestCreateTrainingJobWorkerCount:
    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    async def test_worker_count_saved_to_db(self, mock_build, mock_create, service, mock_db):
        tenant = _make_tenant()
        image = _make_image()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant)]
        mock_build.return_value = {"metadata": {"name": "test"}}

        job = await service.create_training_job(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="dist-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=1,
            worker_count=4,
        )

        assert job.worker_count == 4

    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    async def test_worker_count_passed_to_builder(self, mock_build, mock_create, service, mock_db):
        tenant = _make_tenant()
        image = _make_image()
        mock_db.execute.side_effect = [_sync_result(image), _sync_result(tenant)]
        mock_build.return_value = {"metadata": {"name": "test"}}

        await service.create_training_job(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            name="dist-job",
            image_id=image.id,
            command="python train.py",
            gpu_count=1,
            worker_count=8,
        )

        call_kwargs = mock_build.call_args[1]
        assert call_kwargs["worker_count"] == 8


class TestStopTrainingJob:
    @patch("app.services.training_job_service.delete_vcjob")
    async def test_stop_distributed_job(self, mock_delete, service, mock_db):
        job = _make_job(
            status=TrainingJobStatus.RUNNING,
            vcjob_name="training-dist-job",
            worker_count=4,
        )
        tenant = _make_tenant()
        mock_db.execute.side_effect = [_sync_result(job), _sync_result(tenant)]

        result = await service.stop_training_job(job.id, job.tenant_id)

        assert result.status == TrainingJobStatus.STOPPED
        mock_delete.assert_called_once()


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
        msg = TrainingJobService._map_failure_message({"exit_code": 137, "reason": "OOMKilled", "message": ""})
        assert "OOM" in msg
        assert "内存" in msg

    def test_exit_code_137(self):
        msg = TrainingJobService._map_failure_message({"exit_code": 137, "reason": "Error", "message": ""})
        assert "SIGKILL" in msg

    def test_image_pull_backoff(self):
        msg = TrainingJobService._map_failure_message({"exit_code": 0, "reason": "ImagePullBackOff", "message": ""})
        assert "镜像拉取失败" in msg

    def test_err_image_pull(self):
        msg = TrainingJobService._map_failure_message({"exit_code": 0, "reason": "ErrImagePull", "message": ""})
        assert "镜像拉取失败" in msg

    def test_container_cannot_run(self):
        msg = TrainingJobService._map_failure_message({"exit_code": 1, "reason": "ContainerCannotRun", "message": ""})
        assert "容器启动失败" in msg

    def test_exit_code_1(self):
        msg = TrainingJobService._map_failure_message({"exit_code": 1, "reason": "Error", "message": ""})
        assert "训练脚本执行错误" in msg

    def test_other_exit_code(self):
        msg = TrainingJobService._map_failure_message({"exit_code": 42, "reason": "Error", "message": ""})
        assert "退出码: 42" in msg

    def test_zero_exit_code_with_reason(self):
        msg = TrainingJobService._map_failure_message({"exit_code": 0, "reason": "Unknown", "message": ""})
        assert "失败" in msg


class TestExtractFailureReason:
    @patch("app.services.training_job_service.get_pod_failure_info")
    @patch("app.services.training_job_service.list_vcjob_pods")
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

    @patch("app.services.training_job_service.get_pod_failure_info")
    @patch("app.services.training_job_service.list_vcjob_pods")
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

    @patch("app.services.training_job_service.get_pod_failure_info")
    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_no_failure_info(self, mock_list_pods, mock_failure_info, service):
        mock_list_pods.return_value = [{"pod_name": "pod-1", "role": "master", "status": "failed"}]
        mock_failure_info.return_value = None

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "未能获取具体失败原因" in result

    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_no_pods(self, mock_list_pods, service):
        mock_list_pods.return_value = []

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "已被清理" in result

    @patch("app.services.training_job_service.list_vcjob_pods")
    async def test_list_pods_exception(self, mock_list_pods, service):
        mock_list_pods.side_effect = Exception("K8s error")

        result = await service._extract_failure_reason("ns", "vcjob-1")
        assert "不可用" in result

    @patch("app.services.training_job_service.get_pod_failure_info")
    @patch("app.services.training_job_service.list_vcjob_pods")
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
    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used")
    async def test_retry_failed_job(self, mock_quota, mock_build, mock_create, service, mock_db):
        original_job = _make_job(status=TrainingJobStatus.FAILED, vcjob_name="training-test-job")
        original_job.hyperparameters = {"lr": "0.001", "epochs": "10"}
        original_job.description = "测试任务"
        original_job.metrics_port = 6006
        tenant = _make_tenant()
        image = _make_image(id=original_job.image_id)

        mock_db.execute.side_effect = [
            _sync_result(original_job),
            _sync_result(image),
            _sync_result(tenant),
        ]
        mock_quota.return_value = {"requests.nvidia.com/gpu": "0"}
        mock_build.return_value = {"metadata": {"name": "test-retry"}}

        result = await service.retry_training_job(original_job.id, original_job.tenant_id, uuid.uuid4())

        assert "retry-" in result.name
        assert result.name.startswith(original_job.name)
        mock_create.assert_called_once()

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
