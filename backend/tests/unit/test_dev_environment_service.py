import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, ExternalServiceException, NotFoundException, QuotaExceededException
from app.core.security import decode_token
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
        "spawner_name": "devenv-testuser-abcd1234",
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
def service(mock_db):
    return DevEnvironmentService(mock_db)


class TestCreateEnvironment:
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_create_cpu_env_success(self, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock
        mock_db.execute.return_value = _sync_result(dev_image)
        # Second execute call for tenant
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant)]

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="my-notebook",
            environment_image_id=dev_image.id,
            gpu_count=0,
        )

        assert env.status == DevEnvironmentStatus.CREATING
        assert env.name == "my-notebook"
        assert env.spawner_name is not None
        assert env.spawner_name.endswith(str(env.id)[:8])
        assert env.environment_image_id == dev_image.id
        assert env.environment_type == "jupyter"
        jh_mock.ensure_user.assert_called_once()
        assert jh_mock.ensure_user.call_args[0][0] == env.spawner_name
        jh_mock.start_server.assert_called_once()
        assert jh_mock.start_server.call_args[0][0] == env.spawner_name
        assert jh_mock.start_server.call_args[1]["namespace"] == "kubeai-default"

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    @patch("app.services.dev_environment_service.get_quota_used")
    async def test_create_gpu_env_quota_check(self, mock_quota, mock_jh_client, service, mock_db):
        tenant = _make_tenant(gpu_limit=10)
        dev_image = _make_dev_env_image()
        mock_quota.return_value = {"requests.nvidia.com/gpu": "3"}
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant)]

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="gpu-notebook",
            environment_image_id=dev_image.id,
            gpu_count=2,
        )

        assert env.status == DevEnvironmentStatus.CREATING

    @patch("app.services.dev_environment_service.get_quota_used")
    async def test_create_gpu_env_quota_exceeded(self, mock_quota, service, mock_db):
        tenant = _make_tenant(gpu_limit=5)
        dev_image = _make_dev_env_image()
        mock_quota.return_value = {"requests.nvidia.com/gpu": "4"}
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

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_create_jupyterhub_failure_cleans_up_user(self, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock(side_effect=Exception("connection refused"))
        jh_mock.delete_user = AsyncMock()
        mock_jh_client.return_value = jh_mock
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant)]

        with pytest.raises(Exception, match="启动失败"):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="my-notebook",
                environment_image_id=dev_image.id,
            )

        jh_mock.delete_user.assert_called_once()

    async def test_create_image_not_found(self, service, mock_db):
        mock_db.execute.return_value = _sync_result(None)

        with pytest.raises(NotFoundException, match="开发环境镜像不存在"):
            await service.create_environment(
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
                username="testuser",
                name="my-notebook",
                environment_image_id=uuid.uuid4(),
            )


class TestStopEnvironment:
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_stop_running_env(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)
        jh_mock = AsyncMock()
        jh_mock.stop_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        await service.stop_environment_async(env.id, env.tenant_id)

        # 重新查询最新状态
        assert env.status == DevEnvironmentStatus.STOPPED
        assert env.stopped_reason == "manual"
        jh_mock.stop_server.assert_called_once()

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_stop_with_idle_timeout_reason(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)
        jh_mock = AsyncMock()
        jh_mock.stop_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        await service.stop_environment_async(env.id, env.tenant_id, stopped_reason="idle_timeout")

        assert env.status == DevEnvironmentStatus.STOPPED
        assert env.stopped_reason == "idle_timeout"

    async def test_stop_api_marks_pending_without_calling_jh(self, service, mock_db):
        """service.stop_environment 是 API 路径: 仅置 PENDING, 不调用 JupyterHub."""
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)

        with patch("app.services.dev_environment_service.get_jupyterhub_client") as mock_jh_client:
            result = await service.stop_environment(env.id, env.tenant_id)
            mock_jh_client.assert_not_called()

        assert result.status == DevEnvironmentStatus.PENDING

    async def test_stop_already_stopped_raises(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPED)
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(ConflictException, match="无法停止"):
            await service.stop_environment(env.id, env.tenant_id)

    async def test_stop_failed_raises(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.FAILED)
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(ConflictException, match="无法停止"):
            await service.stop_environment(env.id, env.tenant_id)


class TestStartEnvironment:
    async def test_start_api_marks_creating_without_calling_jh(self, service, mock_db):
        """service.start_environment 是 API 路径: 仅置 CREATING, 不调用 JupyterHub."""
        env = _make_env(status=DevEnvironmentStatus.STOPPED)
        mock_db.execute.return_value = _sync_result(env)

        with patch("app.services.dev_environment_service.get_jupyterhub_client") as mock_jh_client:
            result = await service.start_environment(env.id, env.tenant_id)
            mock_jh_client.assert_not_called()

        assert result.status == DevEnvironmentStatus.CREATING

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_start_stopped_env(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPED)
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        await service.start_environment_async(env.id, env.tenant_id)

        jh_mock.ensure_user.assert_called_once()
        jh_mock.start_server.assert_called_once()
        assert jh_mock.start_server.call_args[1]["namespace"] == "kubeai-default"

    async def test_start_running_raises(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(ConflictException, match="只有已停止"):
            await service.start_environment(env.id, env.tenant_id)

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    @patch("app.services.dev_environment_service.get_quota_used")
    async def test_start_gpu_env_quota_check(self, mock_quota, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPED, gpu_count=2)
        tenant = _make_tenant(id=env.tenant_id, gpu_limit=10)
        user = _make_user(id=env.created_by)
        mock_quota.return_value = {"requests.nvidia.com/gpu": "5"}
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        await service.start_environment_async(env.id, env.tenant_id)
        # 不会自动变 RUNNING (task 路径交给 JupyterHub 后续同步)
        assert env.status in (
            DevEnvironmentStatus.STOPPED,
            DevEnvironmentStatus.CREATING,
        )


class TestDeleteEnvironment:
    async def test_delete_api_only_validates(self, service, mock_db):
        """service.delete_environment 是 API 路径: 仅校验存在性, 不调用 JupyterHub."""
        env = _make_env()
        mock_db.execute.return_value = _sync_result(env)

        with patch("app.services.dev_environment_service.get_jupyterhub_client") as mock_jh_client:
            result = await service.delete_environment(env.id, env.tenant_id)
            mock_jh_client.assert_not_called()
            mock_db.delete.assert_not_called()

        assert result.id == env.id

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_delete_cleanup(self, mock_jh_client, service, mock_db):
        env = _make_env()
        mock_db.execute.return_value = _sync_result(env)
        jh_mock = AsyncMock()
        jh_mock.stop_server = AsyncMock()
        jh_mock.delete_user = AsyncMock()
        mock_jh_client.return_value = jh_mock

        await service.delete_environment_async(env.id, env.tenant_id)

        jh_mock.stop_server.assert_called_once()
        jh_mock.delete_user.assert_called_once()
        mock_db.delete.assert_called_once()


class TestGetAccessUrl:
    async def test_running_env_creates_open_ticket(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING, access_url="http://jupyter/user/test/")
        mock_db.execute.return_value = _sync_result(env)

        with patch("app.services.dev_environment_service.settings") as mock_settings:
            mock_settings.JUPYTERHUB_BASE_URL = "http://localhost:30801"
            mock_settings.DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS = 60
            ticket = await service.create_open_ticket(env.id, env.tenant_id, env.created_by)

        payload = decode_token(ticket)
        assert payload["purpose"] == "dev_environment_open"
        assert payload["env_id"] == str(env.id)
        assert payload["tenant_id"] == str(env.tenant_id)
        assert payload["spawner_name"] == env.spawner_name

    async def test_open_ticket_builds_hub_forced_login_url_for_vscode(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING, environment_type="vscode")
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(env)]

        with patch("app.services.dev_environment_service.settings") as mock_settings:
            mock_settings.JUPYTERHUB_BASE_URL = "http://localhost:30801"
            mock_settings.DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS = 60
            ticket = await service.create_open_ticket(env.id, env.tenant_id, env.created_by)
            url, spawner_name = await service.build_hub_login_url_from_ticket(
                ticket,
                env.id,
                login_token="login-token",
            )

        assert spawner_name == env.spawner_name
        assert (
            url == "http://localhost:30801/hub/login?"
            "login_token=login-token&next=%2Fhub%2Fuser-redirect%2Fcodeserver%2F"
        )

    async def test_open_ticket_builds_hub_forced_login_url_for_jupyter(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING, environment_type="jupyter")
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(env)]

        with patch("app.services.dev_environment_service.settings") as mock_settings:
            mock_settings.JUPYTERHUB_BASE_URL = "http://localhost:30801"
            mock_settings.DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS = 60
            ticket = await service.create_open_ticket(env.id, env.tenant_id, env.created_by)
            url, spawner_name = await service.build_hub_login_url_from_ticket(
                ticket,
                env.id,
                login_token="login-token",
            )

        assert spawner_name == env.spawner_name
        assert url == "http://localhost:30801/hub/login?login_token=login-token&next=%2Fhub%2Fuser-redirect%2Flab"

    async def test_open_ticket_builds_hub_forced_login_url_for_rstudio(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING, environment_type="rstudio")
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(env)]

        with patch("app.services.dev_environment_service.settings") as mock_settings:
            mock_settings.JUPYTERHUB_BASE_URL = "http://localhost:30801"
            mock_settings.DEV_ENV_OPEN_TICKET_EXPIRE_SECONDS = 60
            ticket = await service.create_open_ticket(env.id, env.tenant_id, env.created_by)
            url, spawner_name = await service.build_hub_login_url_from_ticket(
                ticket,
                env.id,
                login_token="login-token",
            )

        assert spawner_name == env.spawner_name
        assert (
            url == "http://localhost:30801/hub/login?login_token=login-token&next=%2Fhub%2Fuser-redirect%2Frstudio%2F"
        )

    async def test_stopped_env_raises(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPED)
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(ConflictException, match="未运行"):
            await service.create_open_ticket(env.id, env.tenant_id, env.created_by)

    async def test_access_url_requires_public_jupyterhub_base_url(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)

        with patch("app.services.dev_environment_service.settings") as mock_settings:
            mock_settings.JUPYTERHUB_BASE_URL = ""
            with pytest.raises(ExternalServiceException, match="访问地址"):
                await service.create_open_ticket(env.id, env.tenant_id, env.created_by)


class TestMapServerStatus:
    def test_none_server_returns_stopped(self):
        from app.integrations.jupyterhub.client import JupyterHubClient

        client = JupyterHubClient()
        assert client.map_server_status(None) == DevEnvironmentStatus.STOPPED

    def test_ready_server_returns_running(self):
        from app.integrations.jupyterhub.client import JupyterHubClient

        client = JupyterHubClient()
        server = {"ready": True, "pending": None}
        assert client.map_server_status(server) == DevEnvironmentStatus.RUNNING

    def test_spawn_pending_returns_creating(self):
        from app.integrations.jupyterhub.client import JupyterHubClient

        client = JupyterHubClient()
        server = {"ready": False, "pending": "spawn"}
        assert client.map_server_status(server) == DevEnvironmentStatus.CREATING

    def test_stopping_pending_returns_creating(self):
        from app.integrations.jupyterhub.client import JupyterHubClient

        client = JupyterHubClient()
        server = {"ready": False, "pending": "stopping"}
        assert client.map_server_status(server) == DevEnvironmentStatus.CREATING


class TestSyncEnvironmentStatus:
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_sync_updates_to_running(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.CREATING)
        jh_mock = AsyncMock()
        jh_mock.get_user.return_value = {
            "name": env.spawner_name,
            "servers": {"": {"ready": True, "url": "http://jupyter/user/test/"}},
        }
        jh_mock.map_server_status = MagicMock(return_value=DevEnvironmentStatus.RUNNING)
        mock_jh_client.return_value = jh_mock

        await service._sync_environment_status(env, "kubeai-default")

        assert env.status == DevEnvironmentStatus.RUNNING
        assert env.access_url == "http://jupyter/user/test/"

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_sync_user_not_found_sets_failed_after_startup_grace(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.CREATING)
        jh_mock = AsyncMock()
        jh_mock.get_user.return_value = None
        mock_jh_client.return_value = jh_mock

        await service._sync_environment_status(env, "kubeai-default")

        assert env.status == DevEnvironmentStatus.FAILED
        assert env.error_message is not None

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_sync_user_not_found_keeps_recent_start_creating(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.CREATING, updated_at=datetime.now(UTC))
        jh_mock = AsyncMock()
        jh_mock.get_user.return_value = None
        mock_jh_client.return_value = jh_mock

        await service._sync_environment_status(env, "kubeai-default")

        assert env.status == DevEnvironmentStatus.CREATING

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_sync_missing_server_marks_creating_failed_after_grace(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.CREATING)
        jh_mock = AsyncMock()
        jh_mock.get_user.return_value = {"name": env.spawner_name, "servers": {}}
        mock_jh_client.return_value = jh_mock

        await service._sync_environment_status(env, "kubeai-default")

        assert env.status == DevEnvironmentStatus.FAILED
        assert env.error_message is not None

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_sync_running_updates_last_active_at(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.CREATING, last_active_at=None)
        jh_mock = AsyncMock()
        jh_last_activity = "2026-05-20T11:30:00.123456Z"
        jh_mock.get_user.return_value = {
            "name": env.spawner_name,
            "servers": {"": {"ready": True, "url": "http://jupyter/user/test/", "last_activity": jh_last_activity}},
        }
        jh_mock.map_server_status = MagicMock(return_value=DevEnvironmentStatus.RUNNING)
        mock_jh_client.return_value = jh_mock

        await service._sync_environment_status(env, "kubeai-default")

        assert env.last_active_at == jh_last_activity
        assert env.status == DevEnvironmentStatus.RUNNING

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_sync_running_fallback_last_active_at(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.CREATING, last_active_at=None)
        jh_mock = AsyncMock()
        jh_mock.get_user.return_value = {
            "name": env.spawner_name,
            "servers": {"": {"ready": True, "url": "http://jupyter/user/test/"}},
        }
        jh_mock.map_server_status = MagicMock(return_value=DevEnvironmentStatus.RUNNING)
        mock_jh_client.return_value = jh_mock

        await service._sync_environment_status(env, "kubeai-default")

        assert env.last_active_at is not None
        assert env.status == DevEnvironmentStatus.RUNNING


def _make_dataset(**overrides):
    from app.models.dataset import Dataset

    defaults = {"name": "test-dataset", "created_by": uuid.uuid4()}
    defaults.update(overrides)
    ds = Dataset(**defaults)
    ds.id = uuid.uuid4()
    ds.created_at = _NOW
    ds.updated_at = _NOW
    return ds


def _make_version(**overrides):
    from app.models.dataset import DatasetVersion

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


class TestCreateEnvironmentWithDatasets:
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_create_with_single_dataset(self, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        dataset = _make_dataset(tenant_id=tenant.id)
        version = _make_version(dataset_id=dataset.id, version_number=1)

        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        # Mock DB queries: dev_image, tenant, dataset, version
        mock_db.execute.side_effect = [
            _sync_result(dev_image),  # _get_dev_environment_image
            _sync_result(tenant),  # _get_tenant_or_fail
            _sync_result(dataset),  # _resolve_dataset_mount dataset
            _sync_result(version),  # _resolve_dataset_mount version
        ]

        datasets = [DatasetMountRequest(dataset_id=dataset.id, version_id=version.id)]
        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="notebook-with-ds",
            environment_image_id=dev_image.id,
            datasets=datasets,
        )

        assert env.mounted_datasets is not None
        assert len(env.mounted_datasets) == 1
        assert env.mounted_datasets[0]["dataset_name"] == "test-dataset"
        assert env.mounted_datasets[0]["mount_path"] == "/kubeai/datasets/test-dataset/v1"
        jh_mock.start_server.assert_called_once()
        call_kwargs = jh_mock.start_server.call_args[1]
        assert call_kwargs["extra_volumes"] is not None
        assert call_kwargs["extra_volume_mounts"] is not None
        # 3 volumes: workspace hostPath + home hostPath + dataset hostPath
        assert len(call_kwargs["extra_volumes"]) == 3
        assert len(call_kwargs["extra_volume_mounts"]) == 3
        assert call_kwargs["extra_volume_mounts"][2]["readOnly"] is True

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_create_with_multiple_datasets(self, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        ds1 = _make_dataset(name="dataset-a", tenant_id=tenant.id)
        v1 = _make_version(dataset_id=ds1.id, version_number=1)
        ds2 = _make_dataset(name="dataset-b", tenant_id=tenant.id)
        v2 = _make_version(dataset_id=ds2.id, version_number=3)

        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        mock_db.execute.side_effect = [
            _sync_result(dev_image),
            _sync_result(tenant),
            _sync_result(ds1),
            _sync_result(v1),
            _sync_result(ds2),
            _sync_result(v2),
        ]

        datasets = [
            DatasetMountRequest(dataset_id=ds1.id, version_id=v1.id),
            DatasetMountRequest(dataset_id=ds2.id, version_id=v2.id),
        ]
        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="multi-ds",
            environment_image_id=dev_image.id,
            datasets=datasets,
        )

        assert env.mounted_datasets is not None
        assert len(env.mounted_datasets) == 2
        names = {md["dataset_name"] for md in env.mounted_datasets}
        assert names == {"dataset-a", "dataset-b"}
        call_kwargs = jh_mock.start_server.call_args[1]
        # 4 volumes: workspace hostPath + home hostPath + 2 dataset hostPaths
        assert len(call_kwargs["extra_volumes"]) == 4
        assert len(call_kwargs["extra_volume_mounts"]) == 4

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_create_without_datasets_backward_compat(self, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock
        mock_db.execute.side_effect = [_sync_result(dev_image), _sync_result(tenant)]

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="no-datasets",
            environment_image_id=dev_image.id,
        )

        assert env.mounted_datasets is None
        call_kwargs = jh_mock.start_server.call_args[1]
        # Always has home + workspace hostPath volumes
        assert call_kwargs["extra_volumes"] is not None
        assert len(call_kwargs["extra_volumes"]) == 2
        assert len(call_kwargs["extra_volume_mounts"]) == 2
        assert call_kwargs["extra_volume_mounts"][0]["mountPath"] == "/kubeai/home"
        assert call_kwargs["extra_volume_mounts"][1]["mountPath"] == "/kubeai/workspace"
        assert call_kwargs["env_vars"]["KUBEAI_ROOT_PATH"] == "/kubeai"
        assert call_kwargs["env_vars"]["KUBEAI_HOME_PATH"] == "/kubeai/home"
        assert call_kwargs["env_vars"]["KUBEAI_WORKSPACE_PATH"] == "/kubeai/workspace"

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_create_uses_latest_version_when_no_version_id(self, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        dataset = _make_dataset(tenant_id=tenant.id)
        version = _make_version(dataset_id=dataset.id, version_number=5)

        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        mock_db.execute.side_effect = [
            _sync_result(dev_image),
            _sync_result(tenant),
            _sync_result(dataset),
            _sync_result(version),
        ]

        datasets = [DatasetMountRequest(dataset_id=dataset.id)]
        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="latest-ver",
            environment_image_id=dev_image.id,
            datasets=datasets,
        )

        assert env.mounted_datasets[0]["version_number"] == 5
        assert env.mounted_datasets[0]["mount_path"] == "/kubeai/datasets/test-dataset/v5"

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_create_nonexistent_dataset_raises(self, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        mock_db.execute.side_effect = [
            _sync_result(dev_image),
            _sync_result(tenant),
            _sync_result(None),  # dataset not found
        ]

        datasets = [DatasetMountRequest(dataset_id=uuid.uuid4())]
        with pytest.raises(NotFoundException, match="数据集不存在"):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="bad-ds",
                environment_image_id=dev_image.id,
                datasets=datasets,
            )

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_create_nonexistent_version_raises(self, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        dev_image = _make_dev_env_image()
        dataset = _make_dataset(tenant_id=tenant.id)
        mock_db.execute.side_effect = [
            _sync_result(dev_image),
            _sync_result(tenant),
            _sync_result(dataset),
            _sync_result(None),  # version not found
        ]

        datasets = [DatasetMountRequest(dataset_id=dataset.id, version_id=uuid.uuid4())]
        with pytest.raises(NotFoundException, match="数据集版本不存在"):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="bad-ver",
                environment_image_id=dev_image.id,
                datasets=datasets,
            )


class TestStartEnvironmentRemount:
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_start_remounts_dataset_host_path(self, mock_jh_client, service, mock_db):
        dataset_id = uuid.uuid4()
        version_id = uuid.uuid4()
        mounted_datasets = [
            {
                "dataset_id": str(dataset_id),
                "dataset_name": "my-data",
                "version_id": str(version_id),
                "version_number": 2,
                "host_path": "/data/kubeai/datasets/default-tenant/my-data/v2",
                "mount_path": "/kubeai/datasets/my-data/v2",
            }
        ]
        env = _make_env(status=DevEnvironmentStatus.STOPPED, mounted_datasets=mounted_datasets)
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        await service.start_environment_async(env.id, env.tenant_id)

        call_kwargs = jh_mock.start_server.call_args[1]
        assert call_kwargs["extra_volumes"] is not None
        # 3 volumes: workspace hostPath + home hostPath + dataset hostPath
        assert len(call_kwargs["extra_volumes"]) == 3
        # Dataset hostPath is the last one
        dataset_vol = call_kwargs["extra_volumes"][2]
        assert "hostPath" in dataset_vol
        assert call_kwargs["extra_volume_mounts"][2]["readOnly"] is True

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_start_no_datasets_only_hostpath_volumes(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPED, mounted_datasets=None)
        tenant = _make_tenant(id=env.tenant_id)
        user = _make_user(id=env.created_by)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant), _sync_result(user)]

        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        await service.start_environment_async(env.id, env.tenant_id)

        call_kwargs = jh_mock.start_server.call_args[1]
        # Only workspace + home hostPath volumes
        assert call_kwargs["extra_volumes"] is not None
        assert len(call_kwargs["extra_volumes"]) == 2
        assert len(call_kwargs["extra_volume_mounts"]) == 2
