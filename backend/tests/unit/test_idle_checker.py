from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.dev_environment import DevEnvironment
from app.models.enums import DevEnvironmentStatus
from app.services.idle_checker import IdleChecker


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
    }
    defaults.update(overrides)
    env = DevEnvironment(**defaults)
    env.id = uuid.uuid4()
    return env


def _db_result(environments):
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = environments
    result.scalars.return_value = scalars_mock
    return result


def _setup_mock_db(mock_session_factory, environments):
    mock_db = AsyncMock()
    mock_db.execute.return_value = _db_result(environments)
    mock_db.commit = AsyncMock()
    mock_session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session_factory.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_db


class TestIdleCheckerCheckAndCull:
    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_stops_idle_environment(self, mock_session_factory, mock_jh_getter):
        last_activity = (datetime.now(UTC) - timedelta(minutes=90)).isoformat()
        env = _make_env()
        _setup_mock_db(mock_session_factory, [env])

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.return_value = last_activity
        jh_mock.stop_server = AsyncMock()
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert env.status == DevEnvironmentStatus.STOPPED
        assert env.stopped_reason == "idle_timeout"
        jh_mock.stop_server.assert_called_once_with(env.spawner_name)

    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_does_not_stop_active_environment(self, mock_session_factory, mock_jh_getter):
        last_activity = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        env = _make_env()
        _setup_mock_db(mock_session_factory, [env])

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.return_value = last_activity
        jh_mock.stop_server = AsyncMock()
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert env.status == DevEnvironmentStatus.RUNNING
        assert env.stopped_reason is None
        jh_mock.stop_server.assert_not_called()

    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_stops_environment_exactly_at_threshold(self, mock_session_factory, mock_jh_getter):
        last_activity = (datetime.now(UTC) - timedelta(minutes=60, seconds=1)).isoformat()
        env = _make_env()
        _setup_mock_db(mock_session_factory, [env])

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.return_value = last_activity
        jh_mock.stop_server = AsyncMock()
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert env.status == DevEnvironmentStatus.STOPPED
        assert env.stopped_reason == "idle_timeout"

    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_skips_environment_with_no_activity(self, mock_session_factory, mock_jh_getter):
        env = _make_env()
        _setup_mock_db(mock_session_factory, [env])

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.return_value = None
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert env.status == DevEnvironmentStatus.RUNNING

    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_does_not_stop_creating_environment(self, mock_session_factory, mock_jh_getter):
        last_activity = (datetime.now(UTC) - timedelta(minutes=90)).isoformat()
        env = _make_env(status=DevEnvironmentStatus.CREATING)
        _setup_mock_db(mock_session_factory, [env])

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.return_value = last_activity
        jh_mock.stop_server = AsyncMock()
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert env.status == DevEnvironmentStatus.CREATING
        jh_mock.stop_server.assert_not_called()

    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_jh_api_error_does_not_affect_other_environments(self, mock_session_factory, mock_jh_getter):
        idle_activity = (datetime.now(UTC) - timedelta(minutes=90)).isoformat()
        env1 = _make_env(spawner_name="devenv-user1-aaa")
        env2 = _make_env(spawner_name="devenv-user2-bbb")
        _setup_mock_db(mock_session_factory, [env1, env2])

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.side_effect = [
            Exception("connection refused"),  # env1 fails
            idle_activity,  # env2 is idle
        ]
        jh_mock.stop_server = AsyncMock()
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert env1.status == DevEnvironmentStatus.RUNNING  # not affected
        assert env2.status == DevEnvironmentStatus.STOPPED
        assert env2.stopped_reason == "idle_timeout"

    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_semaphore_limits_concurrency(self, mock_session_factory, mock_jh_getter):
        envs = [_make_env(spawner_name=f"devenv-user{i}-{i:04x}") for i in range(10)]
        concurrent_count = 0
        max_concurrent = 0
        _setup_mock_db(mock_session_factory, envs)

        async def track_concurrency(username):
            nonlocal concurrent_count, max_concurrent
            concurrent_count += 1
            max_concurrent = max(max_concurrent, concurrent_count)
            await asyncio.sleep(0.01)
            concurrent_count -= 1
            return (datetime.now(UTC) - timedelta(minutes=10)).isoformat()

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.side_effect = track_concurrency
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert max_concurrent <= 5

    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_no_environments_checked_does_not_commit(self, mock_session_factory, mock_jh_getter):
        mock_db = _setup_mock_db(mock_session_factory, [])

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        mock_db.commit.assert_not_called()

    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_stop_server_error_does_not_crash(self, mock_session_factory, mock_jh_getter):
        idle_activity = (datetime.now(UTC) - timedelta(minutes=90)).isoformat()
        env = _make_env()
        _setup_mock_db(mock_session_factory, [env])

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.return_value = idle_activity
        jh_mock.stop_server.side_effect = Exception("delete failed")
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert env.status == DevEnvironmentStatus.RUNNING  # not changed due to stop error


class TestIdleCheckerStartStop:
    async def test_start_creates_task(self):
        checker = IdleChecker()
        checker.start()
        assert checker._task is not None
        assert not checker._task.done()
        await checker.stop()

    async def test_stop_cancels_task(self):
        checker = IdleChecker()
        checker.start()
        await checker.stop()
        assert checker._task.done()

    async def test_start_when_already_running_is_noop(self):
        checker = IdleChecker()
        checker.start()
        first_task = checker._task
        checker.start()
        assert checker._task is first_task
        await checker.stop()

    async def test_stop_when_not_started_is_noop(self):
        checker = IdleChecker()
        await checker.stop()  # should not raise


class TestIdleCheckerNaiveTimestamp:
    @patch("app.services.idle_checker.get_jupyterhub_client")
    @patch("app.services.idle_checker.async_session_factory")
    async def test_handles_naive_timestamp_as_utc(self, mock_session_factory, mock_jh_getter):
        naive_time = (datetime.now(UTC) - timedelta(minutes=90)).replace(tzinfo=None)
        env = _make_env()
        _setup_mock_db(mock_session_factory, [env])

        jh_mock = AsyncMock()
        jh_mock.get_server_last_activity.return_value = naive_time.isoformat()
        jh_mock.stop_server = AsyncMock()
        mock_jh_getter.return_value = jh_mock

        checker = IdleChecker()
        await checker._check_and_cull_idle()

        assert env.status == DevEnvironmentStatus.STOPPED
        assert env.stopped_reason == "idle_timeout"
