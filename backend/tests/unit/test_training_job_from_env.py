import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import BadRequestException, NotFoundException
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus
from app.models.image import Image
from app.models.tenant import Tenant
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
    img.id = overrides.get("id", uuid.uuid4())
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


def _make_environment(**overrides):
    defaults = {
        "tenant_id": uuid.uuid4(),
        "created_by": uuid.uuid4(),
        "name": "test-env",
        "image": "pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
        "gpu_count": 2,
        "cpu": "4",
        "memory": "16Gi",
        "status": DevEnvironmentStatus.RUNNING,
    }
    defaults.update(overrides)
    env = DevEnvironment(**defaults)
    env.id = overrides.get("id", uuid.uuid4())
    env.created_at = _NOW
    env.updated_at = _NOW
    return env


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


class TestCreateFromEnvironmentSuccess:
    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used")
    async def test_success_inherits_image_and_datasets(self, mock_quota, mock_build, mock_create, service, mock_db):
        tenant = _make_tenant()
        env = _make_environment(tenant_id=tenant.id)
        ds_id = uuid.uuid4()
        ver_id = uuid.uuid4()
        env.mounted_datasets = [
            {
                "dataset_id": str(ds_id),
                "dataset_name": "mnist",
                "version_id": str(ver_id),
                "version_number": 1,
                "pvc_name": "dataset-mnist-v1",
                "mount_path": "/data/datasets/mnist/v1",
            }
        ]
        image = _make_image(image_ref=env.image)
        user = _make_user()

        from app.models.dataset import Dataset, DatasetVersion

        dataset = Dataset(name="mnist", tenant_id=tenant.id)
        dataset.id = ds_id
        dataset.created_at = _NOW
        dataset.updated_at = _NOW

        version = DatasetVersion(dataset_id=ds_id, version_number=1, total_size_bytes=1024)
        version.id = ver_id
        version.created_at = _NOW
        version.updated_at = _NOW

        mock_db.execute.side_effect = [
            _sync_result(env),  # _get_environment_or_fail
            _sync_result(image),  # _resolve_image_from_env
            _sync_result(image),  # _get_image_or_fail (in create_training_job)
            _sync_result(dataset),  # _get_dataset_or_fail
            _sync_result(version),  # _get_version_or_fail
            _sync_result(tenant),  # _get_tenant_or_fail
            _sync_result(user),  # _get_user_or_fail
        ]
        mock_quota.return_value = {"requests.nvidia.com/gpu": "0"}
        mock_build.return_value = {"metadata": {"name": "test"}}
        mock_create.return_value = None

        # Need to mock pvc_exists for dataset PVC check
        with patch("app.services.training_job_service.pvc_exists", return_value=True):
            job = await service.create_from_environment(
                tenant_id=tenant.id,
                user_id=user.id,
                environment_id=env.id,
                name="from-env-job",
                command="python train.py",
            )

        assert job.source == "dev_environment"
        assert job.source_env_id == env.id
        assert job.gpu_count == 2  # inherited from env
        assert job.cpu == "4"  # inherited from env
        assert job.memory == "16Gi"  # inherited from env
        mock_create.assert_called_once()

    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used")
    async def test_user_overrides_parameters(self, mock_quota, mock_build, mock_create, service, mock_db):
        tenant = _make_tenant()
        env = _make_environment(tenant_id=tenant.id)
        user = _make_user()
        override_image_id = uuid.uuid4()
        override_dataset_id = uuid.uuid4()
        override_dataset_version_id = uuid.uuid4()

        from app.models.dataset import Dataset, DatasetVersion

        dataset = Dataset(name="override-ds", tenant_id=tenant.id)
        dataset.id = override_dataset_id
        dataset.created_at = _NOW
        dataset.updated_at = _NOW

        version = DatasetVersion(dataset_id=override_dataset_id, version_number=2, total_size_bytes=1024)
        version.id = override_dataset_version_id
        version.created_at = _NOW
        version.updated_at = _NOW

        mock_db.execute.side_effect = [
            _sync_result(env),  # _get_environment_or_fail
            _sync_result(_make_image(id=override_image_id)),  # _get_image_or_fail
            _sync_result(dataset),  # _get_dataset_or_fail
            _sync_result(version),  # _get_version_or_fail
            _sync_result(tenant),  # _get_tenant_or_fail
            _sync_result(user),  # _get_user_or_fail
        ]
        mock_quota.return_value = {"requests.nvidia.com/gpu": "0"}
        mock_build.return_value = {"metadata": {"name": "test"}}

        with patch("app.services.training_job_service.pvc_exists", return_value=True):
            job = await service.create_from_environment(
                tenant_id=tenant.id,
                user_id=user.id,
                environment_id=env.id,
                name="override-job",
                command="python train.py",
                image_id=override_image_id,
                dataset_id=override_dataset_id,
                dataset_version_id=override_dataset_version_id,
                gpu_count=4,
                cpu="8",
                memory="32Gi",
            )

        assert job.image_id == override_image_id
        assert job.dataset_id == override_dataset_id
        assert job.gpu_count == 4
        assert job.cpu == "8"
        assert job.memory == "32Gi"
        assert job.source == "dev_environment"


class TestCreateFromEnvironmentImageResolution:
    async def test_image_not_registered_raises(self, service, mock_db):
        tenant = _make_tenant()
        env = _make_environment(
            tenant_id=tenant.id,
            image="custom/unknown:v1",
        )
        mock_db.execute.side_effect = [
            _sync_result(env),
            _sync_result(None),  # _resolve_image_from_env finds no match
        ]

        with pytest.raises(BadRequestException, match="未在平台镜像仓库中注册"):
            await service.create_from_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                environment_id=env.id,
                name="bad-image-job",
                command="python train.py",
            )

    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used")
    async def test_image_resolution_finds_tenant_and_platform_images(
        self, mock_quota, mock_build, mock_create, service, mock_db
    ):
        tenant = _make_tenant()
        env = _make_environment(
            tenant_id=tenant.id,
            image="pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime",
        )
        # Platform-level image (tenant_id=None)
        platform_image = _make_image(image_ref=env.image)
        platform_image.tenant_id = None
        platform_image.created_at = _NOW
        platform_image.updated_at = _NOW

        user = _make_user()

        mock_db.execute.side_effect = [
            _sync_result(env),
            _sync_result(platform_image),  # _resolve_image_from_env
            _sync_result(platform_image),  # _get_image_or_fail
            _sync_result(tenant),
            _sync_result(user),
        ]
        mock_quota.return_value = {"requests.nvidia.com/gpu": "0"}
        mock_build.return_value = {"metadata": {"name": "test"}}

        job = await service.create_from_environment(
            tenant_id=tenant.id,
            user_id=user.id,
            environment_id=env.id,
            name="platform-image-job",
            command="python train.py",
        )

        assert job.source == "dev_environment"
        mock_create.assert_called_once()


class TestCreateFromEnvironmentDatasetResolution:
    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used")
    async def test_no_mounted_datasets_no_dataset_id(self, mock_quota, mock_build, mock_create, service, mock_db):
        tenant = _make_tenant()
        env = _make_environment(tenant_id=tenant.id)
        env.mounted_datasets = None
        image = _make_image(image_ref=env.image)
        user = _make_user()

        mock_db.execute.side_effect = [
            _sync_result(env),
            _sync_result(image),  # _resolve_image_from_env
            _sync_result(image),  # _get_image_or_fail
            _sync_result(tenant),
            _sync_result(user),
        ]
        mock_quota.return_value = {"requests.nvidia.com/gpu": "0"}
        mock_build.return_value = {"metadata": {"name": "test"}}

        job = await service.create_from_environment(
            tenant_id=tenant.id,
            user_id=user.id,
            environment_id=env.id,
            name="no-dataset-job",
            command="python train.py",
        )

        assert job.dataset_id is None
        assert job.source == "dev_environment"


class TestCreateFromEnvironmentStatusCheck:
    async def test_non_running_environment_rejected(self, service, mock_db):
        tenant = _make_tenant()
        env = _make_environment(
            tenant_id=tenant.id,
            status=DevEnvironmentStatus.STOPPED,
        )
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(BadRequestException, match="运行中"):
            await service.create_from_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                environment_id=env.id,
                name="stopped-env-job",
                command="python train.py",
            )

    async def test_nonexistent_environment_raises(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="开发环境不存在"):
            await service.create_from_environment(
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                environment_id=uuid.uuid4(),
                name="no-env-job",
                command="python train.py",
            )


class TestCreateFromEnvironmentSourceFields:
    @patch("app.services.training_job_service.create_vcjob")
    @patch("app.services.training_job_service.build_vcjob")
    @patch("app.services.training_job_service.get_quota_used")
    async def test_source_fields_written_correctly(self, mock_quota, mock_build, mock_create, service, mock_db):
        tenant = _make_tenant()
        env = _make_environment(tenant_id=tenant.id)
        env.mounted_datasets = None
        image = _make_image(image_ref=env.image)
        user = _make_user()

        mock_db.execute.side_effect = [
            _sync_result(env),
            _sync_result(image),
            _sync_result(image),
            _sync_result(tenant),
            _sync_result(user),
        ]
        mock_quota.return_value = {"requests.nvidia.com/gpu": "0"}
        mock_build.return_value = {"metadata": {"name": "test"}}

        job = await service.create_from_environment(
            tenant_id=tenant.id,
            user_id=user.id,
            environment_id=env.id,
            name="source-test-job",
            command="python train.py",
        )

        assert job.source == "dev_environment"
        assert job.source_env_id == env.id
