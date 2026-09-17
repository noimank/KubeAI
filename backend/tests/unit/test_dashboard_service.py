import uuid
from unittest.mock import AsyncMock, MagicMock

from app.services.dashboard_service import DashboardService


class TestRecentTrainingJobs:
    """概览页最近训练任务与训练任务列表同口径: 排除超参调优 trial 任务."""

    async def test_excludes_tuning_source(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        await DashboardService(db)._get_recent_training_jobs(uuid.uuid4())

        params = db.execute.call_args.args[0].compile().params
        assert "tuning" in params.values()
