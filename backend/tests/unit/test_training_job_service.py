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
