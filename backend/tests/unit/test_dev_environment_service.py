import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import (
    ConflictException,
    ExternalServiceException,
    NotFoundException,
    QuotaExceededException,
)
from app.models.dataset import Dataset, DatasetVersion
from app.models.dev_environment import DevEnvironment
from app.models.dev_environment_image import DevEnvironmentImage
from app.models.enums import DevEnvironmentStatus
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.dev_environment import DatasetMountRequest
from app.services.dev_environment_service import DevEnvironmentService

_NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)
_DEFAULT_IMAGE_ID = uuid.uuid4()


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
    t.id = overrides.get("id", uuid.uuid4())
    t.created_at = _NOW
    t.updated_at = _NOW
    return t


def _make_dev_env_image(**overrides):
    defaults = {
        "name": "Jupyter PyTorch",
        "environment_type": "jupyter",
        "image_ref": "jupyter/pytorch:latest",
        "default_cpu": "2",
        "default_memory": "4Gi",
        "default_gpu_count": 0,
        "is_enabled": True,
    }
    defaults.update(overrides)
    img = DevEnvironmentImage(**defaults)
    img.id = overrides.get("id", _DEFAULT_IMAGE_ID)
    img.created_at = _NOW
    img.updated_at = _NOW
    return img


def _make_env(**overrides):
    defaults = {
        "tenant_id": uuid.uuid4(),
        "created_by": uuid.uuid4(),
        "name": "test-env",
        "image": "jupyter/pytorch:latest",
        "gpu_count": 0,
        "cpu": "2",
        "memory": "4Gi",
        "status": DevEnvironmentStatus.RUNNING,
        "environment_image_id": _DEFAULT_IMAGE_ID,
        "environment_type": "jupyter",
    }
    defaults.update(overrides)
    env = DevEnvironment(**defaults)
    env.id = uuid.uuid4()
    env.created_at = overrides.get("created_at", _NOW)
    env.updated_at = overrides.get("updated_at", _NOW)
    return env


def _make_user(**overrides):
    defaults = {
        "username": "testuser",
        "email": "test@example.com",
        "hashed_password": "fakehash",
    }
    defaults.update(overrides)
    u = User(**defaults)
    u.id = overrides.get("id", uuid.uuid4())
    u.created_at = _NOW
    u.updated_at = _NOW
    return u


def _make_dataset(**overrides):
    defaults = {"name": "test-dataset", "created_by": uuid.uuid4()}
    defaults.update(overrides)
    ds = Dataset(**defaults)
    ds.id = uuid.uuid4()
    ds.created_at = _NOW
    ds.updated_at = _NOW
    return ds


def _make_version(**overrides):
    defaults = {
        "dataset_id": uuid.uuid4(),
        "version_number": 1,
        "storage_path": "/data/test",
        "total_size_bytes": 1024 * 1024 * 100,
        "created_by": uuid.uuid4(),
    }
    defaults.update(overrides)
    v = DatasetVersion(**defaults)
    v.id = uuid.uuid4()
    v.created_at = _NOW
    v.updated_at = _NOW
    return v


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def mock_publish_status_changed():
    with patch(
        "app.services.dev_environment_service.publish_status_changed",
        new=AsyncMock(),
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_ensure_registry_pull_secret():
    with patch(
        "app.services.dev_environment_service.ensure_registry_pull_secret",
        new=AsyncMock(return_value="registry-pull-secret"),
    ) as m:
        yield m


@pytest.fixture(autouse=True)
def mock_create_tenant_network_policy():
    with patch(
        "app.services.dev_environment_service.create_tenant_network_policy",
        new=AsyncMock(),
    ) as m:
        yield m


@pytest.fixture
def mock_dev_pod_manager():
    """Patches get_dev_pod_manager() — the native-Pod lifecycle singleton."""
    manager = AsyncMock()
    with patch(
        "app.services.dev_environment_service.get_dev_pod_manager",
        return_value=manager,
    ):
        yield manager


@pytest.fixture
def service(mock_db):
    return DevEnvironmentService(mock_db)


class TestCreateEnvironment:
    """create_environment only persists a PENDING record; provisioning runs in a task."""

    async def test_create_writes_pending_and_no_pod(self, mock_dev_pod_manager, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant)]

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="my-notebook",
            environment_image_id=dev_image.id,
            gpu_count=0,
        )

        assert env.status == DevEnvironmentStatus.PENDING
        assert env.name == "my-notebook"
        assert env.environment_image_id == dev_image.id
        assert env.environment_type == "jupyter"
        # No pod is created at create time — provisioning is deferred to the task.
        mock_dev_pod_manager.create.assert_not_called()

    @patch(
        "app.services.dev_environment_service.get_quota_used",
        new=AsyncMock(return_value={"requests.nvidia.com/gpu": "0"}),
    )
    async def test_create_gpu_within_quota(self, mock_dev_pod_manager, service, mock_db):
        tenant = _make_tenant(gpu_limit=10)
        dev_image = _make_dev_env_image()
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant)]

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="gpu-notebook",
            environment_image_id=dev_image.id,
            gpu_count=2,
        )

        assert env.status == DevEnvironmentStatus.PENDING

    @patch(
        "app.services.dev_environment_service.get_quota_used",
        new=AsyncMock(return_value={"requests.nvidia.com/gpu": "4"}),
    )
    async def test_create_gpu_quota_exceeded(self, mock_dev_pod_manager, service, mock_db):
        tenant = _make_tenant(gpu_limit=5)
        dev_image = _make_dev_env_image()
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant)]

        with pytest.raises(QuotaExceededException):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="gpu-notebook",
                environment_image_id=dev_image.id,
                gpu_count=2,
            )

    async def test_create_image_not_found(self, mock_dev_pod_manager, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="开发环境镜像不存在"):
            await service.create_environment(
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                username="testuser",
                name="my-notebook",
                environment_image_id=uuid.uuid4(),
            )

    async def test_create_duplicate_name_conflict(self, mock_dev_pod_manager, service, mock_db):
        from sqlalchemy.exc import IntegrityError

        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant)]
        mock_db.commit.side_effect = IntegrityError("orig", {}, Exception("uniq"))

        with pytest.raises(ConflictException, match="已存在"):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="dup",
                environment_image_id=dev_image.id,
            )


class TestProvisionEnvironment:
    """provision_environment: PENDING → STARTING and creates the native dev pod."""

    async def test_provision_creates_pod_and_marks_starting(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.PENDING)
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        result = await service.provision_environment(env.id, env.tenant_id)

        assert result.status == DevEnvironmentStatus.STARTING
        mock_dev_pod_manager.create.assert_awaited_once()
        create_kwargs = mock_dev_pod_manager.create.call_args[1]
        assert create_kwargs["env_id"] == env.id
        assert create_kwargs["namespace"] == "kubeai-default"
        assert create_kwargs["image"] == env.image
        assert create_kwargs["image_pull_secret"] == "registry-pull-secret"
        assert create_kwargs["node_selector"] == {"kubeai": "true"}

    async def test_provision_skips_when_not_pending(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STARTING)
        mock_db.execute.return_value = _sync_result(env)

        await service.provision_environment(env.id, env.tenant_id)

        mock_dev_pod_manager.create.assert_not_called()

    @patch(
        "app.services.dev_environment_service.get_quota_used",
        new=AsyncMock(return_value={"requests.nvidia.com/gpu": "0"}),
    )
    async def test_provision_gpu_env_quota_ok(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.PENDING, gpu_count=2)
        tenant = _make_tenant(id=env.tenant_id, gpu_limit=10)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        await service.provision_environment(env.id, env.tenant_id)

        mock_dev_pod_manager.create.assert_awaited_once()

    async def test_provision_start_failure_marks_failed(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.PENDING)
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]
        mock_dev_pod_manager.create.side_effect = Exception("boom")

        with pytest.raises(ExternalServiceException, match="启动失败"):
            await service.provision_environment(env.id, env.tenant_id)

        assert env.status == DevEnvironmentStatus.FAILED
        assert env.error_message is not None


class TestStartEnvironment:
    async def test_start_api_marks_starting_without_pod(self, mock_dev_pod_manager, service, mock_db):
        """start_environment (API path) only transitions STOPPED → STARTING."""
        env = _make_env(status=DevEnvironmentStatus.STOPPED)
        mock_db.execute.return_value = _sync_result(env)

        result = await service.start_environment(env.id, env.tenant_id)

        assert result.status == DevEnvironmentStatus.STARTING
        mock_dev_pod_manager.create.assert_not_called()

    async def test_start_async_creates_pod(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STARTING)
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        await service.start_environment_async(env.id, env.tenant_id)

        mock_dev_pod_manager.create.assert_awaited_once()

    async def test_start_async_skips_when_not_starting(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)

        await service.start_environment_async(env.id, env.tenant_id)

        mock_dev_pod_manager.create.assert_not_called()

    async def test_start_running_raises(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(ConflictException, match="只有已停止"):
            await service.start_environment(env.id, env.tenant_id)


class TestStopEnvironment:
    async def test_stop_api_marks_stopping_without_pod(self, mock_dev_pod_manager, service, mock_db):
        """stop_environment (API path) only transitions → STOPPING."""
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)

        result = await service.stop_environment(env.id, env.tenant_id)

        assert result.status == DevEnvironmentStatus.STOPPING
        assert result.stopped_reason == "manual"
        mock_dev_pod_manager.stop_server.assert_not_called()

    async def test_stop_async_deletes_pod(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPING)
        tenant = _make_tenant(id=env.tenant_id)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant)]

        await service.stop_environment_async(env.id, env.tenant_id)

        mock_dev_pod_manager.stop_server.assert_awaited_once_with(env.id, "kubeai-default")

    async def test_stop_async_with_idle_reason(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPING)
        tenant = _make_tenant(id=env.tenant_id)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant)]

        await service.stop_environment_async(env.id, env.tenant_id, stopped_reason="idle_timeout")

        mock_dev_pod_manager.stop_server.assert_awaited_once()

    async def test_stop_async_swallows_k8s_failure(self, mock_dev_pod_manager, service, mock_db):
        """A K8s failure during stop must not raise — the user can retry."""
        env = _make_env(status=DevEnvironmentStatus.STOPPING)
        tenant = _make_tenant(id=env.tenant_id)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant)]
        mock_dev_pod_manager.stop_server.side_effect = Exception("k8s down")

        await service.stop_environment_async(env.id, env.tenant_id)  # no raise

    async def test_stop_already_stopped_raises(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPED)
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(ConflictException, match="无法停止"):
            await service.stop_environment(env.id, env.tenant_id)

    async def test_stop_failed_raises(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.FAILED)
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(ConflictException, match="无法停止"):
            await service.stop_environment(env.id, env.tenant_id)


class TestDeleteEnvironment:
    async def test_delete_api_only_validates(self, mock_dev_pod_manager, service, mock_db):
        """delete_environment (API path) only checks existence."""
        env = _make_env()
        mock_db.execute.return_value = _sync_result(env)

        result = await service.delete_environment(env.id, env.tenant_id)

        assert result.id == env.id
        mock_dev_pod_manager.delete.assert_not_called()
        mock_db.delete.assert_not_called()

    async def test_delete_async_removes_pod_and_row(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env()
        tenant = _make_tenant(id=env.tenant_id)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant)]

        await service.delete_environment_async(env.id, env.tenant_id)

        mock_dev_pod_manager.delete.assert_awaited_once_with(env.id, "kubeai-default")
        mock_db.delete.assert_called_once_with(env)
        mock_db.commit.assert_awaited()

    async def test_delete_async_tolerates_k8s_failure(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env()
        tenant = _make_tenant(id=env.tenant_id)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant)]
        mock_dev_pod_manager.delete.side_effect = Exception("k8s down")

        await service.delete_environment_async(env.id, env.tenant_id)  # no raise
        mock_db.delete.assert_called_once_with(env)


class TestDatasetMounts:
    """Dataset resolution (create) + volume rebuilding (provision/start)."""

    async def test_create_resolves_single_dataset(self, mock_dev_pod_manager, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        dataset = _make_dataset(tenant_id=tenant.id)
        version = _make_version(dataset_id=dataset.id, version_number=1)
        mock_db.execute.side_effect = [
            _sync_result(dev_image),
            _sync_result(tenant),
            _sync_result(dataset),
            _sync_result(version),
        ]

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="notebook-with-ds",
            environment_image_id=dev_image.id,
            datasets=[DatasetMountRequest(dataset_id=dataset.id, version_id=version.id)],
        )

        assert env.mounted_datasets is not None
        assert len(env.mounted_datasets) == 1
        assert env.mounted_datasets[0]["dataset_name"] == "test-dataset"
        assert env.mounted_datasets[0]["mount_path"] == "/kubeai/datasets/test-dataset/v1"

    async def test_create_uses_latest_version_when_no_version_id(self, mock_dev_pod_manager, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        dataset = _make_dataset(tenant_id=tenant.id)
        version = _make_version(dataset_id=dataset.id, version_number=5)
        mock_db.execute.side_effect = [
            _sync_result(dev_image),
            _sync_result(tenant),
            _sync_result(dataset),
            _sync_result(version),
        ]

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="latest-ver",
            environment_image_id=dev_image.id,
            datasets=[DatasetMountRequest(dataset_id=dataset.id)],
        )

        assert env.mounted_datasets[0]["version_number"] == 5
        assert env.mounted_datasets[0]["mount_path"] == "/kubeai/datasets/test-dataset/v5"

    async def test_create_nonexistent_dataset_raises(self, mock_dev_pod_manager, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant), _sync_result(None)]

        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="bad-ds",
                environment_image_id=dev_image.id,
                datasets=[DatasetMountRequest(dataset_id=uuid.uuid4())],
            )

    async def test_create_nonexistent_version_raises(self, mock_dev_pod_manager, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        dataset = _make_dataset(tenant_id=tenant.id)
        mock_db.execute.side_effect = [
            _sync_result(dev_image),
            _sync_result(tenant),
            _sync_result(dataset),
            _sync_result(None),
        ]

        with pytest.raises(NotFoundException, match="数据集版本不存在"):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="bad-ver",
                environment_image_id=dev_image.id,
                datasets=[DatasetMountRequest(dataset_id=dataset.id, version_id=uuid.uuid4())],
            )

    async def test_provision_single_dataset_mounts_three_volumes(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(
            status=DevEnvironmentStatus.PENDING,
            mounted_datasets=[
                {
                    "dataset_id": str(uuid.uuid4()),
                    "dataset_name": "my-data",
                    "version_id": str(uuid.uuid4()),
                    "version_number": 2,
                    "host_path": "/data/kubeai/datasets/default-tenant/my-data/v2",
                    "mount_path": "/kubeai/datasets/my-data/v2",
                }
            ],
        )
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        await service.provision_environment(env.id, env.tenant_id)

        create_kwargs = mock_dev_pod_manager.create.call_args[1]
        # home + workspace + 1 dataset
        assert len(create_kwargs["volumes"]) == 3
        assert len(create_kwargs["volume_mounts"]) == 3
        assert create_kwargs["volume_mounts"][2]["readOnly"] is True
        # Dataset is the last hostPath volume
        assert "hostPath" in create_kwargs["volumes"][2]

    async def test_provision_multiple_datasets_mounts_four_volumes(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(
            status=DevEnvironmentStatus.PENDING,
            mounted_datasets=[
                {
                    "dataset_name": "dataset-a",
                    "version_number": 1,
                    "host_path": "/data/a",
                    "mount_path": "/kubeai/datasets/dataset-a/v1",
                },
                {
                    "dataset_name": "dataset-b",
                    "version_number": 3,
                    "host_path": "/data/b",
                    "mount_path": "/kubeai/datasets/dataset-b/v3",
                },
            ],
        )
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        await service.provision_environment(env.id, env.tenant_id)

        create_kwargs = mock_dev_pod_manager.create.call_args[1]
        # home + workspace + 2 datasets
        assert len(create_kwargs["volumes"]) == 4

    async def test_provision_without_datasets_has_two_hostpath_volumes(self, mock_dev_pod_manager, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.PENDING, mounted_datasets=None)
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        await service.provision_environment(env.id, env.tenant_id)

        create_kwargs = mock_dev_pod_manager.create.call_args[1]
        assert len(create_kwargs["volumes"]) == 2
        assert len(create_kwargs["volume_mounts"]) == 2
        assert create_kwargs["volume_mounts"][0]["mountPath"] == "/kubeai/home"
        assert create_kwargs["volume_mounts"][1]["mountPath"] == "/kubeai/workspace"
        env_vars = create_kwargs["env_vars"]
        assert env_vars["KUBEAI_ROOT_PATH"] == "/kubeai"
        assert env_vars["KUBEAI_HOME_PATH"] == "/kubeai/home"
        assert env_vars["KUBEAI_WORKSPACE_PATH"] == "/kubeai/workspace"

    async def test_start_async_remounts_datasets(self, mock_dev_pod_manager, service, mock_db):
        """Restarting a stopped env rebuilds the dataset volumes for the new pod."""
        env = _make_env(
            status=DevEnvironmentStatus.STARTING,
            mounted_datasets=[
                {
                    "dataset_name": "my-data",
                    "version_number": 2,
                    "host_path": "/data/kubeai/datasets/default-tenant/my-data/v2",
                    "mount_path": "/kubeai/datasets/my-data/v2",
                }
            ],
        )
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        await service.start_environment_async(env.id, env.tenant_id)

        create_kwargs = mock_dev_pod_manager.create.call_args[1]
        assert len(create_kwargs["volumes"]) == 3
        assert create_kwargs["volume_mounts"][2]["readOnly"] is True
