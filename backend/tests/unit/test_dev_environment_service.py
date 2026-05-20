import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException, QuotaExceededException
from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus
from app.models.tenant import Tenant
from app.services.dev_environment_service import DevEnvironmentService

_NOW = datetime(2026, 5, 20, 12, 0, 0, tzinfo=UTC)


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
        "jupyterhub_user": "devenv-testuser-abcd1234",
        "pvc_name": "workspace-testuser-abcd1234",
    }
    defaults.update(overrides)
    env = DevEnvironment(**defaults)
    env.id = uuid.uuid4()
    env.created_at = _NOW
    env.updated_at = _NOW
    return env


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.commit = AsyncMock()
    db.delete = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return DevEnvironmentService(mock_db)


class TestCreateEnvironment:
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    @patch("app.services.dev_environment_service.create_pvc")
    async def test_create_cpu_env_success(self, mock_create_pvc, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock
        mock_db.execute.return_value = _sync_result(tenant)

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="my-notebook",
            image="jupyter/pytorch:latest",
            gpu_count=0,
        )

        assert env.status == DevEnvironmentStatus.CREATING
        assert env.name == "my-notebook"
        mock_create_pvc.assert_called_once()
        jh_mock.ensure_user.assert_called_once()
        jh_mock.start_server.assert_called_once()

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    @patch("app.services.dev_environment_service.create_pvc")
    @patch("app.services.dev_environment_service.get_quota_used")
    async def test_create_gpu_env_quota_check(self, mock_quota, mock_create_pvc, mock_jh_client, service, mock_db):
        tenant = _make_tenant(gpu_limit=10)
        mock_quota.return_value = {"requests.nvidia.com/gpu": "3"}
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock
        mock_db.execute.return_value = _sync_result(tenant)

        env = await service.create_environment(
            tenant_id=tenant.id,
            user_id=uuid.uuid4(),
            username="testuser",
            name="gpu-notebook",
            image="jupyter/pytorch:latest",
            gpu_count=2,
        )

        assert env.status == DevEnvironmentStatus.CREATING

    @patch("app.services.dev_environment_service.get_quota_used")
    async def test_create_gpu_env_quota_exceeded(self, mock_quota, service, mock_db):
        tenant = _make_tenant(gpu_limit=5)
        mock_quota.return_value = {"requests.nvidia.com/gpu": "4"}
        mock_db.execute.return_value = _sync_result(tenant)

        with pytest.raises(QuotaExceededException):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="gpu-notebook",
                image="jupyter/pytorch:latest",
                gpu_count=2,
            )

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    @patch("app.services.dev_environment_service.create_pvc")
    async def test_create_jupyterhub_failure_sets_failed(self, mock_create_pvc, mock_jh_client, service, mock_db):
        tenant = _make_tenant()
        jh_mock = AsyncMock()
        jh_mock.ensure_user = AsyncMock()
        jh_mock.start_server = AsyncMock(side_effect=Exception("connection refused"))
        mock_jh_client.return_value = jh_mock
        mock_db.execute.return_value = _sync_result(tenant)

        with pytest.raises(Exception, match="JupyterHub"):
            await service.create_environment(
                tenant_id=tenant.id,
                user_id=uuid.uuid4(),
                username="testuser",
                name="my-notebook",
                image="jupyter/pytorch:latest",
            )


class TestStopEnvironment:
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_stop_running_env(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING)
        mock_db.execute.return_value = _sync_result(env)
        jh_mock = AsyncMock()
        jh_mock.stop_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        result = await service.stop_environment(env.id, env.tenant_id)

        assert result.status == DevEnvironmentStatus.STOPPED
        jh_mock.stop_server.assert_called_once()

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
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_start_stopped_env(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPED)
        tenant = _make_tenant(id=env.tenant_id)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant)]
        jh_mock = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        result = await service.start_environment(env.id, env.tenant_id)

        assert result.status == DevEnvironmentStatus.CREATING
        jh_mock.start_server.assert_called_once()

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
        mock_quota.return_value = {"requests.nvidia.com/gpu": "5"}
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant)]
        jh_mock = AsyncMock()
        jh_mock.start_server = AsyncMock()
        mock_jh_client.return_value = jh_mock

        result = await service.start_environment(env.id, env.tenant_id)
        assert result.status == DevEnvironmentStatus.CREATING


class TestDeleteEnvironment:
    @patch("app.services.dev_environment_service.delete_pvc")
    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_delete_cleanup(self, mock_jh_client, mock_delete_pvc, service, mock_db):
        env = _make_env()
        mock_db.execute.return_value = _sync_result(env)
        tenant = _make_tenant(id=env.tenant_id)
        mock_db.execute.side_effect = [_sync_result(env), _sync_result(tenant)]
        jh_mock = AsyncMock()
        jh_mock.stop_server = AsyncMock()
        jh_mock.delete_user = AsyncMock()
        mock_jh_client.return_value = jh_mock

        await service.delete_environment(env.id, env.tenant_id)

        jh_mock.stop_server.assert_called_once()
        jh_mock.delete_user.assert_called_once()
        mock_delete_pvc.assert_called_once()
        mock_db.delete.assert_called_once()


class TestGetNotebookUrl:
    async def test_running_env_returns_cached_url(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.RUNNING, notebook_url="http://jupyter/user/test/")
        mock_db.execute.return_value = _sync_result(env)

        url = await service.get_notebook_url(env.id, env.tenant_id)

        assert url == "http://jupyter/user/test/"

    async def test_stopped_env_raises(self, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.STOPPED)
        mock_db.execute.return_value = _sync_result(env)

        with pytest.raises(ConflictException, match="未运行"):
            await service.get_notebook_url(env.id, env.tenant_id)


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
            "name": env.jupyterhub_user,
            "servers": {"": {"ready": True, "url": "http://jupyter/user/test/"}},
        }
        jh_mock.map_server_status = MagicMock(return_value=DevEnvironmentStatus.RUNNING)
        mock_jh_client.return_value = jh_mock

        await service._sync_environment_status(env, "kubeai-default")

        assert env.status == DevEnvironmentStatus.RUNNING
        assert env.notebook_url == "http://jupyter/user/test/"

    @patch("app.services.dev_environment_service.get_jupyterhub_client")
    async def test_sync_user_not_found_sets_stopped(self, mock_jh_client, service, mock_db):
        env = _make_env(status=DevEnvironmentStatus.CREATING)
        jh_mock = AsyncMock()
        jh_mock.get_user.return_value = None
        mock_jh_client.return_value = jh_mock

        await service._sync_environment_status(env, "kubeai-default")

        assert env.status == DevEnvironmentStatus.STOPPED
