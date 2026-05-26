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
