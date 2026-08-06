import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from optuna.trial import TrialState

from app.core.exceptions import QuotaExceededException
from app.models.enums import TrainingJobStatus, TuningStudyStatus, TuningTrialState
from app.models.tuning import TuningStudy, TuningTrial
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
        "pruning_enabled": False,
        "pruning_config": None,
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


def _make_frozen_trial(number, state, value=None, params=None):
    """Mock optuna FrozenTrial (单目标)."""
    t = MagicMock()
    t.number = number
    t.state = state
    t.values = [value] if value is not None else None
    t.params = params or {}
    return t


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.delete = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.execute = AsyncMock()
    db.execute.return_value = MagicMock()
    return db


class TestResolveRunningTrial:
    """单 trial 决策: Optuna 未终态 trial → 看关联 job 决定 tell/skip."""

    async def test_succeeded_with_metric_completes(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(3, TrialState.RUNNING)
        trial = _make_trial(study.id, trial_number=3)
        job = MagicMock()
        job.id = trial.training_job_id
        job.status = TrainingJobStatus.SUCCEEDED
        job.finished_at = None
        service._read_metric_from_job = AsyncMock(return_value=0.5)
        optuna_study = MagicMock()

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            action, value = await service._resolve_running_trial(study, optuna_study, frozen, trial, {job.id: job})

        assert (action, value) == ("complete", 0.5)
        mock_tell.assert_awaited_once_with(optuna_study, 3, 0.5)
        assert trial.state == TuningTrialState.COMPLETE.value
        assert trial.value == 0.5
        assert trial.error_message is None

    async def test_succeeded_no_metric_within_grace_skips(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(0, TrialState.RUNNING)
        trial = _make_trial(study.id, trial_number=0)
        job = MagicMock()
        job.id = trial.training_job_id
        job.status = TrainingJobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC) - timedelta(seconds=10)  # grace 内
        service._read_metric_from_job = AsyncMock(return_value=None)

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            action, _ = await service._resolve_running_trial(study, MagicMock(), frozen, trial, {job.id: job})

        assert action == "skip"
        mock_tell.assert_not_awaited()

    async def test_succeeded_no_metric_beyond_grace_fails(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(0, TrialState.RUNNING)
        trial = _make_trial(study.id, trial_number=0)
        job = MagicMock()
        job.id = trial.training_job_id
        job.status = TrainingJobStatus.SUCCEEDED
        job.finished_at = datetime.now(UTC) - timedelta(seconds=9999)  # 超 grace
        service._read_metric_from_job = AsyncMock(return_value=None)
        optuna_study = MagicMock()

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            action, _ = await service._resolve_running_trial(study, optuna_study, frozen, trial, {job.id: job})

        assert action == "fail"
        mock_tell.assert_awaited_once_with(optuna_study, 0, None)
        assert trial.state == TuningTrialState.FAILED.value
        assert "val_loss" in trial.error_message

    async def test_failed_job_fails(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(1, TrialState.RUNNING)
        trial = _make_trial(study.id, trial_number=1)
        job = MagicMock()
        job.id = trial.training_job_id
        job.status = TrainingJobStatus.FAILED
        job.error_message = "OOM"
        optuna_study = MagicMock()

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            action, _ = await service._resolve_running_trial(study, optuna_study, frozen, trial, {job.id: job})

        assert action == "fail"
        mock_tell.assert_awaited_once_with(optuna_study, 1, None)
        assert trial.state == TuningTrialState.FAILED.value
        assert trial.error_message == "OOM"

    async def test_running_job_skips(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(2, TrialState.RUNNING)
        trial = _make_trial(study.id, trial_number=2)
        job = MagicMock()
        job.id = trial.training_job_id
        job.status = TrainingJobStatus.RUNNING

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            action, _ = await service._resolve_running_trial(study, MagicMock(), frozen, trial, {job.id: job})

        assert action == "skip"  # 留给 prune
        mock_tell.assert_not_awaited()

    async def test_no_platform_trial_fails(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(4, TrialState.RUNNING)
        optuna_study = MagicMock()

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            action, _ = await service._resolve_running_trial(study, optuna_study, frozen, None, {})

        assert action == "fail"
        mock_tell.assert_awaited_once_with(optuna_study, 4, None)

    async def test_job_deleted_fails(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(5, TrialState.RUNNING)
        trial = _make_trial(study.id, trial_number=5)
        optuna_study = MagicMock()

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            action, _ = await service._resolve_running_trial(study, optuna_study, frozen, trial, {})  # job 不在 map

        assert action == "fail"
        mock_tell.assert_awaited_once_with(optuna_study, 5, None)
        assert trial.state == TuningTrialState.FAILED.value
        assert trial.error_message == "trial 训练任务已被删除"


class TestReconcileTrials:
    async def test_finished_trial_syncs_platform_without_tell(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(1, TrialState.COMPLETE, value=0.4)
        trial = _make_trial(study.id, trial_number=1, state=TuningTrialState.PENDING.value)
        service._load_platform_trial_map = AsyncMock(return_value={1: trial})
        service._load_jobs_map = AsyncMock(return_value={})

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            still_running = await service._reconcile_trials(study, MagicMock(), [frozen])

        assert still_running == 0
        mock_tell.assert_not_awaited()
        assert trial.state == TuningTrialState.COMPLETE.value
        assert trial.value == 0.4
        assert study.best_value == 0.4

    async def test_orphan_no_platform_row_tells_fail(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study()
        frozen = _make_frozen_trial(7, TrialState.RUNNING)
        service._load_platform_trial_map = AsyncMock(return_value={})
        service._load_jobs_map = AsyncMock(return_value={})
        optuna_study = MagicMock()

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            still_running = await service._reconcile_trials(study, optuna_study, [frozen])

        mock_tell.assert_awaited_once_with(optuna_study, 7, None)
        assert still_running == 0

    async def test_best_value_picks_min_for_minimize(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(direction="minimize")
        frozens = [
            _make_frozen_trial(0, TrialState.COMPLETE, value=0.5),
            _make_frozen_trial(1, TrialState.COMPLETE, value=0.3),
            _make_frozen_trial(2, TrialState.COMPLETE, value=0.4),
        ]
        service._load_platform_trial_map = AsyncMock(return_value={})
        service._load_jobs_map = AsyncMock(return_value={})

        with patch("app.services.tuning_service.study_tell", AsyncMock()):
            await service._reconcile_trials(study, MagicMock(), frozens)

        assert study.best_value == 0.3


class TestSpawnTrials:
    async def test_respects_n_jobs_concurrency(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(n_jobs=3, n_trials=10)
        service._count_running_trials = AsyncMock(return_value=2)  # 运行中 2, n_jobs=3 → 只补 1
        service._create_trial_job = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.training_service.check_gpu_quota_for_tenant = AsyncMock()

        with (
            patch(
                "app.services.tuning_service.study_ask",
                AsyncMock(return_value=MagicMock(number=2, params={"lr": 0.01})),
            ),
            patch("app.tasks.training_job_tasks.enqueue_submit_training_job", AsyncMock()) as mock_enqueue,
        ):
            await service._spawn_trials(study, MagicMock(), {}, {"dropout": 0.5}, asked=0)

        mock_enqueue.assert_awaited_once()
        db.add.assert_called_once()

    async def test_stops_at_n_trials_cap(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(n_jobs=4, n_trials=5)
        service._count_running_trials = AsyncMock(return_value=0)
        service._create_trial_job = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
        service.training_service.check_gpu_quota_for_tenant = AsyncMock()

        with (
            patch(
                "app.services.tuning_service.study_ask",
                AsyncMock(return_value=MagicMock(number=3, params={"lr": 0.01})),
            ),
            patch("app.tasks.training_job_tasks.enqueue_submit_training_job", AsyncMock()) as mock_enqueue,
        ):
            await service._spawn_trials(study, MagicMock(), {}, {}, asked=4)  # 4 < 5 → 补 1

        mock_enqueue.assert_awaited_once()

    async def test_asked_at_n_trials_does_not_spawn(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(n_trials=5)
        service._count_running_trials = AsyncMock(return_value=0)

        with (
            patch("app.services.tuning_service.study_ask", AsyncMock()) as mock_ask,
            patch("app.tasks.training_job_tasks.enqueue_submit_training_job", AsyncMock()) as mock_enqueue,
        ):
            await service._spawn_trials(study, MagicMock(), {}, {}, asked=5)  # 5 not < 5

        mock_ask.assert_not_awaited()
        mock_enqueue.assert_not_awaited()
        db.add.assert_not_called()

    async def test_gpu_quota_exceeded_stops_spawning_without_error(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(n_trials=10)
        service._count_running_trials = AsyncMock(return_value=0)
        service.training_service.check_gpu_quota_for_tenant = AsyncMock(
            side_effect=QuotaExceededException("GPU 配额不足")
        )

        with (
            patch("app.services.tuning_service.study_ask", AsyncMock()) as mock_ask,
            patch("app.tasks.training_job_tasks.enqueue_submit_training_job", AsyncMock()) as mock_enqueue,
        ):
            await service._spawn_trials(study, MagicMock(), {}, {}, asked=0)

        mock_ask.assert_not_awaited()
        mock_enqueue.assert_not_awaited()
        db.add.assert_not_called()

    async def test_enqueue_failure_rolls_back_and_aborts_without_orphan(self):
        """enqueue 失败 (如 broker 不可用) 不得留下 PENDING 孤儿 trial 卡死 study.

        回滚本次未生效写入 + 调用 _abort_trial_spawn 清理已 commit 的 job/trial 行 + 告知 Optuna FAIL,
        且本 tick 不再补发 (break), 异常不向上抛出.
        """
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(n_trials=10)
        job_id = uuid.uuid4()
        service._count_running_trials = AsyncMock(return_value=0)
        service._create_trial_job = AsyncMock(return_value=MagicMock(id=job_id, vcjob_name=None))
        service.training_service.check_gpu_quota_for_tenant = AsyncMock()
        service._abort_trial_spawn = AsyncMock()

        with (
            patch(
                "app.services.tuning_service.study_ask",
                AsyncMock(return_value=MagicMock(number=0, params={"lr": 0.01})),
            ),
            patch(
                "app.tasks.training_job_tasks.enqueue_submit_training_job",
                AsyncMock(side_effect=RuntimeError("broker down")),
            ) as mock_enqueue,
        ):
            # 不应抛出
            await service._spawn_trials(study, MagicMock(), {}, {}, asked=0)

        mock_enqueue.assert_awaited_once()
        db.add.assert_called_once()
        db.rollback.assert_awaited_once()
        service._abort_trial_spawn.assert_awaited_once()
        assert service._abort_trial_spawn.call_args.args[1:] == (0, job_id)


class TestDriveStudy:
    async def test_completes_when_n_trials_reached_and_no_running(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(n_trials=2)
        frozens = [
            _make_frozen_trial(0, TrialState.COMPLETE, value=0.5),
            _make_frozen_trial(1, TrialState.COMPLETE, value=0.3),
        ]

        with (
            patch("app.services.tuning_service.load_study", AsyncMock()),
            patch("app.services.tuning_service.study_trials", AsyncMock(return_value=frozens)),
            patch.object(service, "_reconcile_trials", AsyncMock(return_value=0)),
            patch.object(service, "_spawn_trials", AsyncMock()) as mock_spawn,
        ):
            await service.drive_study(study)

        assert study.status == TuningStudyStatus.COMPLETED.value
        mock_spawn.assert_not_awaited()

    async def test_spawns_when_below_n_trials(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(n_trials=5)
        frozens = [_make_frozen_trial(0, TrialState.COMPLETE, value=0.5)]

        with (
            patch("app.services.tuning_service.load_study", AsyncMock()),
            patch("app.services.tuning_service.study_trials", AsyncMock(return_value=frozens)),
            patch.object(service, "_reconcile_trials", AsyncMock(return_value=0)),
            patch.object(service, "_spawn_trials", AsyncMock()) as mock_spawn,
        ):
            await service.drive_study(study)

        assert study.status == TuningStudyStatus.RUNNING.value
        mock_spawn.assert_awaited_once()
        assert mock_spawn.await_args.args[-1] == 1  # asked = len(trials)


class TestComputeBestValue:
    def test_minimize_returns_min(self):
        assert TuningService._compute_best_value("minimize", [0.5, 0.3, 0.4]) == 0.3

    def test_maximize_returns_max(self):
        assert TuningService._compute_best_value("maximize", [0.5, 0.3]) == 0.5

    def test_empty_returns_none(self):
        assert TuningService._compute_best_value("minimize", []) is None


class TestReadMetric:
    async def test_read_metric_returns_latest_by_step(self):
        db = _mock_db()
        service = TuningService(db)
        job = MagicMock()
        job.id = uuid.uuid4()
        db.execute.return_value.scalar_one_or_none.return_value = "run-1"
        mlflow_client = AsyncMock()
        mlflow_client.get_metric_history.return_value = [
            {"step": 1, "value": 0.5},
            {"step": 0, "value": 0.9},
            {"step": 2, "value": 0.3},
        ]

        with patch("app.services.tuning_service.get_mlflow_client", return_value=mlflow_client):
            value = await service._read_metric_from_job(job, "val_loss")

        assert value == 0.3  # 按 step 排序后取最大 step (2) 的值
        mlflow_client.get_metric_history.assert_awaited_once_with(run_id="run-1", metric_key="val_loss")

    async def test_no_run_id_returns_none(self):
        db = _mock_db()
        service = TuningService(db)
        job = MagicMock()
        job.id = uuid.uuid4()
        db.execute.return_value.scalar_one_or_none.return_value = None

        with patch("app.services.tuning_service.get_mlflow_client") as mock_client:
            value = await service._read_metric_from_job(job, "val_loss")

        assert value is None
        mock_client.assert_not_called()


class TestPruneRunningTrials:
    """阈值剪枝: 运行中 trial 的最新 intermediate 与已完成 trial 终值 median 比较."""

    def _setup(
        self,
        service,
        study,
        *,
        completed,
        series=None,
        job_status=TrainingJobStatus.RUNNING,
        frozen_number=3,
    ):
        frozen = _make_frozen_trial(frozen_number, TrialState.RUNNING)
        trial = _make_trial(study.id, trial_number=frozen_number)
        job = MagicMock()
        job.status = job_status
        service._completed_values = AsyncMock(return_value=completed)
        service._get_trial_by_number = AsyncMock(return_value=trial)
        service._get_job = AsyncMock(return_value=job)
        service._read_metric_series = AsyncMock(return_value=series or [(0, 0.9), (1, 0.8), (2, 0.85)])
        service._stop_trial_job = AsyncMock()
        return frozen, trial

    async def test_below_threshold_does_not_prune(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(
            pruning_enabled=True,
            pruning_config={"n_startup_trials": 5, "n_warmup_steps": 1, "interval": 1, "n_min_trials": 2},
        )
        frozen, _ = self._setup(service, study, completed=[0.2, 0.3])  # len 2 < n_startup 5

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            await service._prune_running_trials(study, MagicMock(), [frozen])

        mock_tell.assert_not_awaited()

    async def test_within_warmup_does_not_prune(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(
            pruning_enabled=True,
            pruning_config={"n_startup_trials": 2, "n_warmup_steps": 5, "interval": 1, "n_min_trials": 2},
        )
        frozen, _ = self._setup(
            service, study, completed=[0.2, 0.3], series=[(0, 0.9), (1, 0.8)]
        )  # latest_step 1 < warmup 5

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            await service._prune_running_trials(study, MagicMock(), [frozen])

        mock_tell.assert_not_awaited()

    async def test_worse_than_median_is_pruned(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(
            pruning_enabled=True,
            direction="minimize",
            pruning_config={"n_startup_trials": 2, "n_warmup_steps": 1, "interval": 1, "n_min_trials": 2},
        )
        optuna_study = MagicMock()
        # completed median 0.25; latest 0.85 > 0.25 → 差 (minimize) → 剪
        frozen, trial = self._setup(service, study, completed=[0.2, 0.3])

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            await service._prune_running_trials(study, optuna_study, [frozen])

        mock_tell.assert_awaited_once_with(optuna_study, 3, state=TrialState.PRUNED)
        assert trial.state == TuningTrialState.PRUNED.value
        service._stop_trial_job.assert_awaited_once()

    async def test_better_than_median_not_pruned(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(
            pruning_enabled=True,
            direction="minimize",
            pruning_config={"n_startup_trials": 2, "n_warmup_steps": 1, "interval": 1, "n_min_trials": 2},
        )
        # completed median 0.25; latest 0.1 < 0.25 → 好 (minimize) → 不剪
        frozen, _ = self._setup(service, study, completed=[0.2, 0.3], series=[(0, 0.5), (1, 0.1)])

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            await service._prune_running_trials(study, MagicMock(), [frozen])

        mock_tell.assert_not_awaited()
        service._stop_trial_job.assert_not_awaited()

    async def test_maximize_direction_prunes_when_below_median(self):
        db = _mock_db()
        service = TuningService(db)
        study = _make_study(
            pruning_enabled=True,
            direction="maximize",
            pruning_config={"n_startup_trials": 2, "n_warmup_steps": 1, "interval": 1, "n_min_trials": 2},
        )
        optuna_study = MagicMock()
        # completed median 0.25; latest 0.1 < 0.25 → 差 (maximize) → 剪
        frozen, trial = self._setup(service, study, completed=[0.2, 0.3], series=[(0, 0.5), (1, 0.1)])

        with patch("app.services.tuning_service.study_tell", AsyncMock()) as mock_tell:
            await service._prune_running_trials(study, optuna_study, [frozen])

        mock_tell.assert_awaited_once_with(optuna_study, 3, state=TrialState.PRUNED)
        assert trial.state == TuningTrialState.PRUNED.value
