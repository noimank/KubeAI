import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.exceptions import ConflictException
from app.models.enums import TuningStudyStatus, TuningTrialState
from app.models.tuning import TuningStudy, TuningTrial
from app.schemas.tuning import TuningStudyCreateRequest
from app.services.tuning_service import TuningService


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
        "sampler_config": None,
        "stopping_config": None,
    }
    defaults.update(overrides)
    return TuningStudy(**defaults)


def _make_trial(study_id, trial_number=0, **overrides):
    defaults = {
        "study_id": study_id,
        "trial_number": trial_number,
        "training_job_id": uuid.uuid4(),
        "params": {"lr": 0.01},
        "state": TuningTrialState.PENDING.value,
    }
    defaults.update(overrides)
    return TuningTrial(**defaults)


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


def _create_req(**overrides):
    defaults = {
        "name": "my-study",
        "direction": "minimize",
        "metric_name": "val_loss",
        "n_trials": 5,
        "n_jobs": 2,
        "search_space": {"lr": {"type": "float", "low": 1e-4, "high": 0.1}},
        "image_id": uuid.uuid4(),
        "command": "python train.py",
    }
    defaults.update(overrides)
    return TuningStudyCreateRequest(**defaults)


class TestCreateStudy:
    async def test_create_study_creates_optuna_study_and_record(self):
        db = _mock_db()
        service = TuningService(db)
        service.training_service.validate_training_image = AsyncMock()

        with patch("app.services.tuning_service.optuna_create_study", AsyncMock()) as mock_create:
            study = await service.create_study(
                _create_req(),
                tenant_id=uuid.uuid4(),
                user_id=uuid.uuid4(),
            )

        mock_create.assert_awaited_once()
        kwargs = mock_create.await_args.kwargs
        assert kwargs["direction"] == "minimize"
        assert kwargs["study_name"].startswith("tuning-")
        assert study.status == TuningStudyStatus.RUNNING.value
        assert study.n_trials == 5
        assert study.search_space["lr"]["type"] == "float"
        db.add.assert_called_once()
        db.commit.assert_awaited()

    async def test_create_study_validates_image_before_optuna(self):
        db = _mock_db()
        service = TuningService(db)
        service.training_service.validate_training_image = AsyncMock()

        with patch("app.services.tuning_service.optuna_create_study", AsyncMock()) as mock_create:
            await service.create_study(_create_req(), tenant_id=uuid.uuid4(), user_id=uuid.uuid4())

        service.training_service.validate_training_image.assert_awaited_once()
        mock_create.assert_awaited_once()

    async def test_create_study_invalid_search_space_raises_bad_request(self):
        from app.core.exceptions import BadRequestException

        db = _mock_db()
        service = TuningService(db)
        service.training_service.validate_training_image = AsyncMock()
        # type 由 pydantic Literal 提前拦截, 此处用 schema 合法但分布非法的输入:
        # float 区间 low > high → optuna FloatDistribution 抛 ValueError.
        req = _create_req(search_space={"lr": {"type": "float", "low": 0.1, "high": 0.01}})
        with pytest.raises(BadRequestException, match="搜索空间非法"):
            await service.create_study(req, tenant_id=uuid.uuid4(), user_id=uuid.uuid4())
        # 搜索空间校验失败时不建 optuna study
        service.training_service.validate_training_image.assert_not_awaited()

    async def test_create_study_persists_sampler_and_stopping_config(self):
        db = _mock_db()
        service = TuningService(db)
        service.training_service.validate_training_image = AsyncMock()

        req = _create_req(
            sampler_config={"type": "random", "seed": 3},
            stopping_config={"study_timeout_seconds": 3600, "trial_timeout_seconds": 600},
        )
        with patch("app.services.tuning_service.optuna_create_study", AsyncMock()):
            study = await service.create_study(req, tenant_id=uuid.uuid4(), user_id=uuid.uuid4())

        assert study.sampler_config == {"type": "random", "seed": 3, "multivariate": False}
        assert study.stopping_config == {"study_timeout_seconds": 3600, "trial_timeout_seconds": 600}
        # 默认不配置 → 存 None
        db2 = _mock_db()
        service2 = TuningService(db2)
        service2.training_service.validate_training_image = AsyncMock()
        with patch("app.services.tuning_service.optuna_create_study", AsyncMock()) as mock_create2:
            study2 = await service2.create_study(_create_req(), tenant_id=uuid.uuid4(), user_id=uuid.uuid4())
        assert study2.sampler_config is None
        assert study2.stopping_config is None
        # 默认 sampler 是 TPE (create 时也透传)
        from optuna.samplers import TPESampler

        assert isinstance(mock_create2.await_args.kwargs["sampler"], TPESampler)

    async def test_create_study_cmaes_on_categorical_rejects(self):
        from app.core.exceptions import BadRequestException

        db = _mock_db()
        service = TuningService(db)
        service.training_service.validate_training_image = AsyncMock()

        req = _create_req(
            sampler_config={"type": "cmaes"},
            search_space={
                "opt": {"type": "categorical", "choices": ["adam", "sgd"]},
                "lr": {"type": "float", "low": 1e-4, "high": 0.1},
            },
        )
        with (
            patch("app.services.tuning_service.optuna_create_study", AsyncMock()) as mock_create,
            pytest.raises(BadRequestException, match="采样器配置非法"),
        ):
            await service.create_study(req, tenant_id=uuid.uuid4(), user_id=uuid.uuid4())

        mock_create.assert_not_awaited()  # 校验失败不建 study


class TestStopDeleteStudy:
    async def test_stop_study_marks_stopped_and_stops_trials(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        db.execute.return_value.scalar_one_or_none.return_value = study
        service._stop_trial_jobs = AsyncMock()

        result = await service.stop_study(study.id, study.tenant_id)

        assert result.status == TuningStudyStatus.STOPPED.value
        service._stop_trial_jobs.assert_awaited_once()

    async def test_stop_study_conflicts_when_not_running(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(status=TuningStudyStatus.COMPLETED.value)
        db.execute.return_value.scalar_one_or_none.return_value = study

        with pytest.raises(ConflictException, match="无法停止"):
            await service.stop_study(study.id, study.tenant_id)

    async def test_delete_study_cleans_trials_and_optuna(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        trial = _make_trial(study.id)
        service._get_study_or_fail = AsyncMock(return_value=study)
        service._list_trials = AsyncMock(return_value=[trial])
        service._job_is_terminal = AsyncMock(return_value=True)
        service.training_service.delete_training_job_record = AsyncMock(
            return_value=("training-x", "kubeai-t", False, "mlflow-exp")
        )

        with (
            patch("app.services.tuning_service.optuna_delete_study", AsyncMock()) as mock_del,
            patch(
                "app.tasks.training_job_tasks.enqueue_delete_training_job",
                AsyncMock(),
            ) as mock_enqueue,
        ):
            await service.delete_study(study.id, study.tenant_id)

        service.training_service.delete_training_job_record.assert_awaited_once_with(
            trial.training_job_id, study.tenant_id
        )
        mock_enqueue.assert_awaited_once()
        mock_del.assert_awaited_once_with(study.optuna_study_name)
        db.delete.assert_called_once_with(study)
        db.commit.assert_awaited()

    async def test_delete_study_conflicts_when_trial_job_running(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        trial = _make_trial(study.id)
        service._get_study_or_fail = AsyncMock(return_value=study)
        service._list_trials = AsyncMock(return_value=[trial])
        service._job_is_terminal = AsyncMock(return_value=False)

        with (
            patch("app.services.tuning_service.optuna_delete_study", AsyncMock()) as mock_del,
            pytest.raises(ConflictException, match="请先停止调优任务"),
        ):
            await service.delete_study(study.id, study.tenant_id)
        mock_del.assert_not_awaited()


class TestPauseResumeStudy:
    async def test_pause_running_sets_paused_and_stops_trials(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        db.execute.return_value.scalar_one_or_none.return_value = study
        service._stop_trial_jobs = AsyncMock()

        with patch("app.tasks.tuning_tasks.enqueue_drive_study", AsyncMock()) as mock_enqueue:
            result = await service.pause_study(study.id, study.tenant_id)

        assert result.status == TuningStudyStatus.PAUSED.value
        service._stop_trial_jobs.assert_awaited_once()
        mock_enqueue.assert_awaited_once_with(study.id)
        # 先置 PAUSED 提交, 再停 trial job (顺序保证并发 drive 不补发)
        assert db.commit.call_count >= 1

    async def test_pause_completed_conflicts(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(status=TuningStudyStatus.COMPLETED.value)
        db.execute.return_value.scalar_one_or_none.return_value = study

        with (
            patch("app.tasks.tuning_tasks.enqueue_drive_study", AsyncMock()),
            pytest.raises(ConflictException, match="无法暂停"),
        ):
            await service.pause_study(study.id, study.tenant_id)

    async def test_resume_paused_sets_running_and_drives(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(status=TuningStudyStatus.PAUSED.value)
        db.execute.return_value.scalar_one_or_none.return_value = study

        with patch("app.tasks.tuning_tasks.enqueue_drive_study", AsyncMock()) as mock_enqueue:
            result = await service.resume_study(study.id, study.tenant_id)

        assert result.status == TuningStudyStatus.RUNNING.value
        mock_enqueue.assert_awaited_once_with(study.id)

    async def test_resume_running_conflicts(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        db.execute.return_value.scalar_one_or_none.return_value = study

        with (
            patch("app.tasks.tuning_tasks.enqueue_drive_study", AsyncMock()),
            pytest.raises(ConflictException, match="无法恢复"),
        ):
            await service.resume_study(study.id, study.tenant_id)
