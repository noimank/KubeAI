from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.enums import TrainingJobStatus
from app.services.resource_cleaner import (
    TERMINAL_STATUSES,
    ResourceCleaner,
)


@pytest.fixture
def cleaner() -> ResourceCleaner:
    return ResourceCleaner()


class TestStaleJobDetection:
    @pytest.mark.asyncio
    async def test_detect_stale_jobs_returns_old_terminal_jobs(self, cleaner: ResourceCleaner) -> None:
        job_id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        now = datetime.now(UTC)

        mock_job = MagicMock()
        mock_job.id = job_id
        mock_job.name = "test-job"
        mock_job.status = TrainingJobStatus.SUCCEEDED.value
        mock_job.finished_at = now - timedelta(days=10)
        mock_job.vcjob_name = "vcjob-test"

        mock_tenant = MagicMock()
        mock_tenant.id = tenant_id
        mock_tenant.display_name = "测试租户"
        mock_tenant.name = "test"
        mock_tenant.k8s_namespace_name = "kubeai-test"

        mock_result = MagicMock()
        mock_result.all.return_value = [(mock_job, mock_tenant)]

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.resource_cleaner.async_session_factory") as mock_factory:
            mock_factory.return_value = mock_db
            stale_jobs = await cleaner.detect_stale_jobs()

        assert len(stale_jobs) == 1
        assert stale_jobs[0].id == job_id
        assert stale_jobs[0].name == "test-job"
        assert stale_jobs[0].days_ago == 10

    @pytest.mark.asyncio
    async def test_detect_stale_jobs_excludes_recent_jobs(self, cleaner: ResourceCleaner) -> None:
        mock_result = MagicMock()
        mock_result.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.return_value = mock_result
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.resource_cleaner.async_session_factory") as mock_factory:
            mock_factory.return_value = mock_db
            stale_jobs = await cleaner.detect_stale_jobs()

        assert len(stale_jobs) == 0


class TestOrphanPVCDetection:
    @pytest.mark.asyncio
    async def test_detect_orphan_pvcs_excludes_known_dataset_pvcs(self, cleaner: ResourceCleaner) -> None:
        from app.integrations.k8s.pvc import PVCInfo

        mock_pvc = PVCInfo(
            name="dataset-mydata-v1",
            namespace="kubeai-test",
            storage="10Gi",
            labels={"kubeai.io/type": "dataset"},
            creation_timestamp="2026-01-01T00:00:00Z",
        )

        mock_dv = MagicMock()
        mock_dv.dataset_id = uuid.uuid4()
        mock_dv.version_number = 1

        mock_ds = MagicMock()
        mock_ds.id = mock_dv.dataset_id
        mock_ds.name = "mydata"

        dv_result = MagicMock()
        dv_result.scalars.return_value.all.return_value = [mock_dv]
        ds_result = MagicMock()
        ds_result.scalars.return_value.all.return_value = [mock_ds]

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [dv_result, ds_result]
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.resource_cleaner.async_session_factory") as mock_factory,
            patch("app.services.resource_cleaner.list_tenant_namespaces", return_value=["kubeai-test"]),
            patch("app.services.resource_cleaner.list_namespace_pvcs", return_value=[mock_pvc]),
        ):
            mock_factory.return_value = mock_db
            orphans = await cleaner.detect_orphan_pvcs()

        assert len(orphans) == 0

    @pytest.mark.asyncio
    async def test_detect_orphan_pvcs_finds_unmounted_pvc(self, cleaner: ResourceCleaner) -> None:
        from app.integrations.k8s.pvc import PVCInfo

        mock_pvc = PVCInfo(
            name="orphan-pvc",
            namespace="kubeai-test",
            storage="5Gi",
            labels={"kubeai.io/type": "workspace"},
            creation_timestamp="2026-01-01T00:00:00Z",
        )

        dv_result = MagicMock()
        dv_result.scalars.return_value.all.return_value = []
        ds_result = MagicMock()
        ds_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [dv_result, ds_result]
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.resource_cleaner.async_session_factory") as mock_factory,
            patch("app.services.resource_cleaner.list_tenant_namespaces", return_value=["kubeai-test"]),
            patch("app.services.resource_cleaner.list_namespace_pvcs", return_value=[mock_pvc]),
            patch("app.services.resource_cleaner.list_namespace_pods_by_pvc", return_value=[]),
        ):
            mock_factory.return_value = mock_db
            orphans = await cleaner.detect_orphan_pvcs()

        assert len(orphans) == 1
        assert orphans[0].name == "orphan-pvc"
        assert orphans[0].orphan_reason == "未被任何 Pod 挂载且不属于已知数据集版本"

    @pytest.mark.asyncio
    async def test_detect_orphan_pvcs_excludes_pvc_with_active_pods(self, cleaner: ResourceCleaner) -> None:
        from app.integrations.k8s.pvc import PVCInfo

        mock_pvc = PVCInfo(
            name="in-use-pvc",
            namespace="kubeai-test",
            storage="5Gi",
            labels={"kubeai.io/type": "workspace"},
            creation_timestamp="2026-01-01T00:00:00Z",
        )

        dv_result = MagicMock()
        dv_result.scalars.return_value.all.return_value = []
        ds_result = MagicMock()
        ds_result.scalars.return_value.all.return_value = []

        mock_db = AsyncMock()
        mock_db.execute.side_effect = [dv_result, ds_result]
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.resource_cleaner.async_session_factory") as mock_factory,
            patch("app.services.resource_cleaner.list_tenant_namespaces", return_value=["kubeai-test"]),
            patch("app.services.resource_cleaner.list_namespace_pvcs", return_value=[mock_pvc]),
            patch("app.services.resource_cleaner.list_namespace_pods_by_pvc", return_value=["pod-1"]),
        ):
            mock_factory.return_value = mock_db
            orphans = await cleaner.detect_orphan_pvcs()

        assert len(orphans) == 0


class TestCleanupPVCs:
    @pytest.mark.asyncio
    async def test_cleanup_pvcs_success(self, cleaner: ResourceCleaner) -> None:
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.resource_cleaner.async_session_factory") as mock_factory,
            patch("app.services.resource_cleaner.delete_pvc", new_callable=AsyncMock),
        ):
            mock_factory.return_value = mock_db
            results = await cleaner.cleanup_pvcs(
                [("kubeai-test", "pvc-1")],
                {"user_id": uuid.uuid4(), "ip_address": ""},
            )

        assert len(results) == 1
        assert results[0].success is True

    @pytest.mark.asyncio
    async def test_cleanup_pvcs_handles_failure(self, cleaner: ResourceCleaner) -> None:
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.__aenter__ = AsyncMock(return_value=mock_db)
        mock_db.__aexit__ = AsyncMock(return_value=False)

        with (
            patch("app.services.resource_cleaner.async_session_factory") as mock_factory,
            patch(
                "app.services.resource_cleaner.delete_pvc", new_callable=AsyncMock, side_effect=Exception("K8s error")
            ),
        ):
            mock_factory.return_value = mock_db
            results = await cleaner.cleanup_pvcs(
                [("kubeai-test", "pvc-1")],
                {"user_id": uuid.uuid4(), "ip_address": ""},
            )

        assert len(results) == 1
        assert results[0].success is False
        assert "K8s error" in results[0].error


class TestResourceCleanerLifecycle:
    def test_terminal_statuses_are_correct(self) -> None:
        assert TrainingJobStatus.SUCCEEDED in TERMINAL_STATUSES
        assert TrainingJobStatus.FAILED in TERMINAL_STATUSES
        assert TrainingJobStatus.STOPPED in TERMINAL_STATUSES
        assert TrainingJobStatus.RUNNING not in TERMINAL_STATUSES
        assert TrainingJobStatus.PENDING not in TERMINAL_STATUSES

    @pytest.mark.asyncio
    async def test_start_and_stop(self, cleaner: ResourceCleaner) -> None:
        cleaner.start()
        assert cleaner._task is not None
        assert not cleaner._task.done()

        await cleaner.stop()
        assert cleaner._task is not None
        assert cleaner._task.done()

    @pytest.mark.asyncio
    async def test_trigger_manual_cleanup(self, cleaner: ResourceCleaner) -> None:
        with patch("app.services.resource_cleaner.ResourceCleaner._run_cleanup", new_callable=AsyncMock):
            await cleaner.trigger_manual_cleanup()
