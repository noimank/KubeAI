import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from optuna.trial import TrialState

from app.core.exceptions import NotFoundException
from app.models.enums import TuningStudyStatus
from app.models.tuning import TuningStudy
from app.services.tuning_service import TuningService, _map_trial_state


def _make_study(**overrides):
    defaults = {
        "tenant_id": uuid.uuid4(),
        "name": "test-study",
        "status": TuningStudyStatus.RUNNING.value,
        "direction": "minimize",
        "metric_name": "val_loss",
        "n_trials": 5,
        "n_jobs": 1,
        "search_space": {"lr": {"type": "float", "low": 1e-4, "high": 0.1}},
        "image_id": uuid.uuid4(),
        "command": "python train.py",
        "gpu_count": 1,
        "gpu_mode": "exclusive",
        "cpu": "4",
        "memory": "8Gi",
        "priority": "normal",
        "worker_count": 1,
        "created_by": uuid.uuid4(),
        "optuna_study_name": "tuning-abc-123",
    }
    defaults.update(overrides)
    return TuningStudy(**defaults)


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


def _make_trial(trial_number, state, values, params, duration=None):
    return SimpleNamespace(
        number=trial_number,
        values=values,
        params=params,
        state=state,
        datetime_start=datetime(2026, 1, 1, tzinfo=UTC),
        datetime_complete=datetime(2026, 1, 1, 1, tzinfo=UTC),
        duration=duration,
    )


class TestGetInsights:
    async def test_maps_history_and_importance(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        optuna_study = MagicMock()
        trials = [
            _make_trial(
                0,
                TrialState.COMPLETE,
                (0.5,),
                {"lr": 0.01},
                duration=timedelta(seconds=3600),
            ),
            _make_trial(1, TrialState.FAIL, None, {"lr": 0.5}),
            _make_trial(2, TrialState.RUNNING, None, {"lr": 0.1}),
        ]

        with (
            patch("app.services.tuning_service.load_study", AsyncMock(return_value=optuna_study)),
            patch("app.services.tuning_service.study_trials", AsyncMock(return_value=trials)),
            patch(
                "app.services.tuning_service.study_param_importances",
                AsyncMock(return_value={"lr": 0.9}),
            ),
        ):
            data = await service.get_insights(study.id, study.tenant_id)

        assert data["importance"] == {"lr": 0.9}
        history = data["history"]
        assert len(history) == 3

        done = history[0]
        assert done["trial_number"] == 0
        assert done["value"] == 0.5
        assert done["params"] == {"lr": 0.01}
        assert done["state"] == "complete"
        assert done["duration_seconds"] == 3600.0
        assert done["datetime_complete"] is not None

        assert history[1]["state"] == "failed"
        assert history[1]["value"] is None
        assert history[1]["duration_seconds"] is None

        assert history[2]["state"] == "running"
        assert history[2]["value"] is None

    async def test_importance_empty_when_insufficient_trials(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        optuna_study = MagicMock()

        with (
            patch("app.services.tuning_service.load_study", AsyncMock(return_value=optuna_study)),
            patch("app.services.tuning_service.study_trials", AsyncMock(return_value=[])),
            patch("app.services.tuning_service.study_param_importances", AsyncMock(return_value={})),
        ):
            data = await service.get_insights(study.id, study.tenant_id)

        assert data["history"] == []
        assert data["importance"] == {}

    async def test_unknown_study_raises_not_found(self):
        db = _mock_db()
        service = TuningService(db)
        db.execute.return_value.scalar_one_or_none.return_value = None

        with (
            patch("app.services.tuning_service.load_study", AsyncMock()) as mock_load,
            pytest.raises(NotFoundException),
        ):
            await service.get_insights(uuid.uuid4(), uuid.uuid4())

        mock_load.assert_not_awaited()


class TestMapTrialState:
    def test_maps_all_states(self):
        assert _map_trial_state(TrialState.COMPLETE) == "complete"
        assert _map_trial_state(TrialState.FAIL) == "failed"
        assert _map_trial_state(TrialState.PRUNED) == "pruned"
        assert _map_trial_state(TrialState.RUNNING) == "running"
        assert _map_trial_state(TrialState.WAITING) == "pending"
