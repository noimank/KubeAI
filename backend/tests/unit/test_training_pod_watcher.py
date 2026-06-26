"""Tests for training_pod_watcher's _on_terminal_status side effects.

P0-2 regression coverage: when a Pod reaches a terminal state (Failed, Succeeded,
or Deleted), the watcher MUST clean up TensorBoard resources for jobs that had
TensorBoard enabled. Without this, the TB Service + APISIX route remain as
orphans pointing at a dead Pod (the Service is hand-created with no TTL, while
the VCJob has a 24h ``ttlSecondsAfterFinished``).

Other side effects (MLflow sync, notification, WebSocket publish) are stubbed
in these tests so we can assert the TensorBoard cleanup contract in isolation.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.enums import TrainingJobStatus
from app.models.tenant import Tenant
from app.models.training_job import TrainingJob

_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
_WATCHER_PATH = "app.integrations.k8s.training_pod_watcher"


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
        "tensorboard_enabled": False,
        "vcjob_name": "training-test-job",
        "status": TrainingJobStatus.RUNNING,
    }
    defaults.update(overrides)
    job = TrainingJob(**defaults)
    job.id = uuid.uuid4()
    job.created_at = _NOW
    job.updated_at = _NOW
    return job


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
    return t


class _ScalarResult:
    """Helper: emulate SQLAlchemy Result.scalar_one_or_none() return value."""

    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _patched_factory_returning(tenant_row):
    """Patch ``async_session_factory`` to yield mock sessions returning ``tenant_row``.

    Each ``async with`` call yields a fresh mock session; ``execute()`` returns
    a Result whose ``scalar_one_or_none()`` returns ``tenant_row``.
    """

    @asynccontextmanager
    async def factory():
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_ScalarResult(tenant_row))
        session.commit = AsyncMock()
        session.flush = AsyncMock()
        session.add = AsyncMock()
        yield session

    return factory


def _mock_service_classes():
    """Build mocks for ExperimentService and NotificationService.

    The watcher's function-level ``from app.services.X import Y`` resolves to
    these mocks when the source-module attribute is patched. ``return_value``
    methods are preconfigured as AsyncMocks so ``await svc.method()`` works.
    """
    mock_exp_cls = MagicMock()
    mock_exp_cls.return_value.sync_experiment_status = AsyncMock()
    mock_exp_cls.return_value.terminate_experiments_for_job = AsyncMock()

    mock_notif_cls = MagicMock()
    mock_notif_cls.return_value.create_training_outcome_notification = AsyncMock()

    return mock_exp_cls, mock_notif_cls


class TestOnTerminalStatusTensorboardCleanup:
    async def _invoke(self, job, tenant, *, tb_delete_side_effect=None):
        """Run ``_on_terminal_status`` with side-effect stubs in place.

        Returns ``(tb_delete_mock, mock_exp_cls, mock_notif_cls)`` for assertions.
        """
        from app.integrations.k8s.tensorboard import get_tensorboard_manager
        from app.integrations.k8s.training_pod_watcher import _on_terminal_status

        mock_exp_cls, mock_notif_cls = _mock_service_classes()
        tb_delete_kw: dict = {"new_callable": AsyncMock}
        if tb_delete_side_effect is not None:
            tb_delete_kw["side_effect"] = tb_delete_side_effect

        with (
            patch(f"{_WATCHER_PATH}.async_session_factory", _patched_factory_returning(tenant)),
            patch("app.services.experiment_service.ExperimentService", mock_exp_cls),
            patch("app.services.notification_service.NotificationService", mock_notif_cls),
            patch(f"{_WATCHER_PATH}._publish_training_status_change", AsyncMock()),
            patch(f"{_WATCHER_PATH}.publish_ws_event", AsyncMock()),
            patch.object(get_tensorboard_manager(), "delete", **tb_delete_kw) as mock_delete,
        ):
            await _on_terminal_status(
                job,
                old_status=TrainingJobStatus.RUNNING,
                new_status=TrainingJobStatus.FAILED,
            )

        return mock_delete, mock_exp_cls, mock_notif_cls

    async def test_cleans_up_tensorboard_when_enabled(self):
        """P0-2 回归: TB 启用 + 进终态 → 调 TB manager.delete(job_id, namespace)."""
        job = _make_job(tensorboard_enabled=True)
        tenant = _make_tenant(id=job.tenant_id, k8s_namespace_name="kubeai-default")
        mock_delete, _, _ = await self._invoke(job, tenant)

        mock_delete.assert_awaited_once()
        # delete(job_id, namespace) 是位置参数调用
        args = mock_delete.await_args.args
        assert len(args) >= 2
        assert args[0] == job.id
        assert args[1] == "kubeai-default"

    async def test_skips_cleanup_when_tensorboard_disabled(self):
        """TB 未启用 → 不查 Tenant, 不调 TB manager.delete."""
        from app.integrations.k8s.tensorboard import get_tensorboard_manager
        from app.integrations.k8s.training_pod_watcher import _on_terminal_status

        job = _make_job(tensorboard_enabled=False)
        tenant = _make_tenant(id=job.tenant_id, k8s_namespace_name="kubeai-default")
        mock_exp_cls, mock_notif_cls = _mock_service_classes()

        with (
            patch(f"{_WATCHER_PATH}.async_session_factory", _patched_factory_returning(tenant)),
            patch("app.services.experiment_service.ExperimentService", mock_exp_cls),
            patch("app.services.notification_service.NotificationService", mock_notif_cls),
            patch(f"{_WATCHER_PATH}._publish_training_status_change", AsyncMock()),
            patch(f"{_WATCHER_PATH}.publish_ws_event", AsyncMock()),
            patch.object(get_tensorboard_manager(), "delete", new_callable=AsyncMock) as mock_delete,
        ):
            await _on_terminal_status(
                job,
                old_status=TrainingJobStatus.RUNNING,
                new_status=TrainingJobStatus.SUCCEEDED,
            )

        mock_delete.assert_not_called()

    async def test_skips_cleanup_when_no_vcjob_name(self):
        """vcjob_name 为 None → VCJob 都没创建过, 不存在 TB Service, 跳过清理."""
        from app.integrations.k8s.tensorboard import get_tensorboard_manager
        from app.integrations.k8s.training_pod_watcher import _on_terminal_status

        job = _make_job(tensorboard_enabled=True, vcjob_name=None)
        tenant = _make_tenant(id=job.tenant_id, k8s_namespace_name="kubeai-default")
        mock_exp_cls, mock_notif_cls = _mock_service_classes()

        with (
            patch(f"{_WATCHER_PATH}.async_session_factory", _patched_factory_returning(tenant)),
            patch("app.services.experiment_service.ExperimentService", mock_exp_cls),
            patch("app.services.notification_service.NotificationService", mock_notif_cls),
            patch(f"{_WATCHER_PATH}._publish_training_status_change", AsyncMock()),
            patch(f"{_WATCHER_PATH}.publish_ws_event", AsyncMock()),
            patch.object(get_tensorboard_manager(), "delete", new_callable=AsyncMock) as mock_delete,
        ):
            await _on_terminal_status(
                job,
                old_status=TrainingJobStatus.RUNNING,
                new_status=TrainingJobStatus.FAILED,
            )

        mock_delete.assert_not_called()

    async def test_missing_namespace_skips_cleanup_safely(self):
        """Tenant.k8s_namespace_name 为 None → 跳过清理 + warning log, 不抛错."""
        from app.integrations.k8s.tensorboard import get_tensorboard_manager
        from app.integrations.k8s.training_pod_watcher import _on_terminal_status

        job = _make_job(tensorboard_enabled=True)
        tenant = _make_tenant(id=job.tenant_id, k8s_namespace_name=None)
        mock_exp_cls, mock_notif_cls = _mock_service_classes()

        with (
            patch(f"{_WATCHER_PATH}.async_session_factory", _patched_factory_returning(tenant)),
            patch("app.services.experiment_service.ExperimentService", mock_exp_cls),
            patch("app.services.notification_service.NotificationService", mock_notif_cls),
            patch(f"{_WATCHER_PATH}._publish_training_status_change", AsyncMock()),
            patch(f"{_WATCHER_PATH}.publish_ws_event", AsyncMock()),
            patch.object(get_tensorboard_manager(), "delete", new_callable=AsyncMock) as mock_delete,
        ):
            # 不应抛错 (namespace 为 None → 早返)
            await _on_terminal_status(
                job,
                old_status=TrainingJobStatus.RUNNING,
                new_status=TrainingJobStatus.FAILED,
            )

        mock_delete.assert_not_called()

    async def test_cleanup_failure_does_not_abort_side_effects(self):
        """TB manager.delete 抛错 → 后续 MLflow / 通知 仍照常执行 (best-effort)."""
        job = _make_job(tensorboard_enabled=True)
        tenant = _make_tenant(id=job.tenant_id, k8s_namespace_name="kubeai-default")
        mock_delete, mock_exp_cls, mock_notif_cls = await self._invoke(
            job,
            tenant,
            tb_delete_side_effect=RuntimeError("TB cleanup boom"),
        )

        # delete 被调用 (且抛错) — 不需要断言 await
        mock_delete.assert_awaited_once()
        # 后续 side effects 仍被调用
        mock_exp_cls.return_value.sync_experiment_status.assert_awaited_once()
        mock_notif_cls.return_value.create_training_outcome_notification.assert_awaited_once()

    async def test_failed_terminates_mlflow_zombie_run(self):
        """任务 FAILED (Pod 被 OOMKilled/强杀) 时主动 KILL MLflow run, 避免僵尸 run.

        脚本来不及 end_run, 若不主动终止, run 永远停在 RUNNING.
        """
        job = _make_job(tensorboard_enabled=False)
        tenant = _make_tenant(id=job.tenant_id, k8s_namespace_name="kubeai-default")
        _, mock_exp_cls, _ = await self._invoke(job, tenant)

        mock_exp_cls.return_value.terminate_experiments_for_job.assert_awaited_once_with(job.id)
