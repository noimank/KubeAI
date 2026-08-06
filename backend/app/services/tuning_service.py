from __future__ import annotations

import contextlib
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from optuna.trial import TrialState
from sqlalchemy import case, func, select

from app.core.clients import get_mlflow_client
from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
    QuotaExceededException,
)
from app.core.optuna import (
    best_trial,
    json_search_space_to_distributions,
    load_study,
    study_ask,
    study_param_importances,
    study_tell,
    study_trials,
)
from app.core.optuna import (
    create_study as optuna_create_study,
)
from app.core.optuna import (
    delete_study as optuna_delete_study,
)
from app.core.redis import _redis_pool, init_redis
from app.models.enums import TrainingJobStatus, TuningStudyStatus, TuningTrialState
from app.models.experiment import Experiment
from app.models.training_job import TrainingJob
from app.models.tuning import TuningStudy, TuningTrial
from app.services.training_job_service import ALLOWED_STOP_STATUSES, TrainingJobService

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.tuning import TuningStudyCreateRequest

logger = logging.getLogger(__name__)

TERMINAL_JOB_STATUSES = {TrainingJobStatus.SUCCEEDED, TrainingJobStatus.FAILED, TrainingJobStatus.STOPPED}
_TERMINAL_STATUS_VALUES = {s.value for s in TERMINAL_JOB_STATUSES}

# Optuna 已终态 trial state (已 tell, reconcile 跳过只同步平台表).
_OPTUNA_FINISHED_STATES = frozenset({TrialState.COMPLETE, TrialState.FAIL, TrialState.PRUNED})

# 平台 trial 终态字符串 (用于进度统计的 finalized_count).
_TRIAL_FINAL_STATES = frozenset(
    {TuningTrialState.COMPLETE.value, TuningTrialState.FAILED.value, TuningTrialState.PRUNED.value}
)

# Optuna TrialState → 平台 trial 状态字符串 (insights / 平台表同步).
_TRIAL_STATE_MAP: dict[TrialState, str] = {
    TrialState.COMPLETE: TuningTrialState.COMPLETE.value,
    TrialState.FAIL: TuningTrialState.FAILED.value,
    TrialState.PRUNED: TuningTrialState.PRUNED.value,
    TrialState.RUNNING: TuningTrialState.RUNNING.value,
    TrialState.WAITING: TuningTrialState.PENDING.value,
}


def _map_trial_state(state: TrialState) -> str:
    return _TRIAL_STATE_MAP[state]


def _within_metric_grace(job: TrainingJob) -> bool:
    """job 终态后是否仍在 metric grace 窗口内 (允许 MLflow 延迟上报)."""
    finished_at = job.finished_at
    if finished_at is None:
        return True
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=UTC)
    return datetime.now(UTC) - finished_at < timedelta(seconds=settings.TUNING_METRIC_GRACE_SECONDS)


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


class TuningService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.training_service = TrainingJobService(db)

    # ── per-study 锁 (串行化 reconcile/prune/spawn) ───────────────────
    @staticmethod
    def _drive_lock_key(study_id: uuid.UUID) -> str:
        return f"tuning:study:{study_id}:drive"

    async def _acquire_drive_lock(self, study_id: uuid.UUID) -> bool:
        """Redis SET NX EX per-study 锁.

        Redis 不可用时放行: 调用方本身基于 Optuna state 幂等, 重叠仅浪费计算——重复 ask 由
        _spawn_trials 的 running 计数兜底, 重复 tell 由 per-trial 隔离吞掉, 不致命.
        """
        if _redis_pool is None:
            await init_redis()
        if _redis_pool is None:
            return True
        try:
            return bool(
                await _redis_pool.set(
                    self._drive_lock_key(study_id),
                    uuid.uuid4().hex,
                    nx=True,
                    ex=settings.TUNING_DRIVE_INTERVAL_SECONDS,
                )
            )
        except Exception:
            return True

    async def _release_drive_lock(self, study_id: uuid.UUID) -> None:
        if _redis_pool is None:
            return
        with contextlib.suppress(Exception):
            await _redis_pool.delete(self._drive_lock_key(study_id))

    async def drive_study_locked(self, study_id: uuid.UUID) -> None:
        """per-study 锁包裹的驱动入口 (供 Taskiq task 调用).

        拿不到锁则跳过 (由兜底 cron / 下一个终态事件接); FAILED study 不再驱动.
        """
        if not await self._acquire_drive_lock(study_id):
            return
        try:
            study = await self._get_study_by_id(study_id)
            if study is None or study.status == TuningStudyStatus.FAILED.value:
                return
            await self.drive_study(study)
        finally:
            await self._release_drive_lock(study_id)

    # ── 创建 ─────────────────────────────────────────────────────────
    async def create_study(
        self,
        req: TuningStudyCreateRequest,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> TuningStudy:
        """校验搜索空间/镜像 → 建 optuna study → 写 tuning_studies 行.

        trial 提交由调度器/终态事件驱动 (drive_study); 端点随后 kiq 一次驱动让首个 trial 尽快启动.
        """
        try:
            json_search_space_to_distributions(
                {k: v.model_dump(exclude_none=True) for k, v in req.search_space.items()}
            )
        except ValueError as exc:
            raise BadRequestException(f"搜索空间非法: {exc}") from exc

        await self.training_service.validate_training_image(req.image_id)

        study_id = uuid.uuid4()
        optuna_study_name = f"tuning-{str(tenant_id)[:8]}-{study_id.hex[:8]}"
        await optuna_create_study(study_name=optuna_study_name, direction=req.direction)

        study = TuningStudy(
            id=study_id,
            tenant_id=tenant_id,
            name=req.name,
            description=req.description,
            created_by=user_id,
            status=TuningStudyStatus.RUNNING.value,
            direction=req.direction,
            metric_name=req.metric_name,
            n_trials=req.n_trials,
            n_jobs=req.n_jobs,
            search_space={k: v.model_dump(exclude_none=True) for k, v in req.search_space.items()},
            image_id=req.image_id,
            dataset_id=req.dataset_id,
            dataset_version_id=req.dataset_version_id,
            command=req.command,
            gpu_count=req.gpu_count,
            gpu_mode=req.gpu_mode,
            cpu=req.cpu,
            memory=req.memory,
            priority=req.priority,
            worker_count=req.worker_count,
            env_vars=req.env_vars,
            optuna_study_name=optuna_study_name,
            pruning_enabled=req.pruning_enabled,
            pruning_config=req.pruning_config.model_dump() if req.pruning_config else None,
        )
        self.db.add(study)
        await self.db.commit()
        await self.db.refresh(study)
        return study

    # ── 查询 ─────────────────────────────────────────────────────────
    async def list_studies(
        self,
        *,
        tenant_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        status: str | None = None,
        name: str | None = None,
    ) -> tuple[list[TuningStudy], int]:
        query = select(TuningStudy).where(TuningStudy.tenant_id == tenant_id)
        if status:
            query = query.where(TuningStudy.status == status)
        if name:
            query = query.where(TuningStudy.name.ilike(f"%{name}%"))

        total_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(total_q)).scalar_one()
        result = await self.db.execute(
            query.order_by(TuningStudy.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_study(self, study_id: uuid.UUID, tenant_id: uuid.UUID) -> TuningStudy:
        return await self._get_study_or_fail(study_id, tenant_id)

    async def get_progress(self, study_id: uuid.UUID) -> dict[str, int]:
        """进度统计: trial 总数 / 已 finalize 数 / 运行中数."""
        return (await self.get_progress_map([study_id]))[study_id]

    async def get_progress_map(self, study_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[str, int]]:
        """批量进度统计 (列表页, 避免 N+1 查询). finalized = state ∈ {complete,failed,pruned}."""
        if not study_ids:
            return {}

        counts: dict[uuid.UUID, dict[str, int]] = {}
        result = await self.db.execute(
            select(
                TuningTrial.study_id,
                func.count(),
                func.sum(case((TuningTrial.state.in_(_TRIAL_FINAL_STATES), 1), else_=0)),
            )
            .where(TuningTrial.study_id.in_(study_ids))
            .group_by(TuningTrial.study_id)
        )
        for sid, cnt, finalized in result.all():
            counts[sid] = {
                "trial_count": int(cnt),
                "finalized_count": int(finalized or 0),
                "running_count": 0,
            }
        run_result = await self.db.execute(
            select(TuningTrial.study_id, func.count())
            .join(TrainingJob, TuningTrial.training_job_id == TrainingJob.id)
            .where(TuningTrial.study_id.in_(study_ids), TrainingJob.status.notin_(_TERMINAL_STATUS_VALUES))
            .group_by(TuningTrial.study_id)
        )
        for sid, running in run_result.all():
            counts.setdefault(sid, {"trial_count": 0, "finalized_count": 0, "running_count": 0})["running_count"] = int(
                running
            )
        for sid in study_ids:
            counts.setdefault(sid, {"trial_count": 0, "finalized_count": 0, "running_count": 0})
        return counts

    async def list_trials(self, study_id: uuid.UUID, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
        await self._get_study_or_fail(study_id, tenant_id)
        result = await self.db.execute(
            select(TuningTrial, TrainingJob)
            .outerjoin(TrainingJob, TuningTrial.training_job_id == TrainingJob.id)
            .where(TuningTrial.study_id == study_id)
            .order_by(TuningTrial.trial_number.asc())
        )
        items: list[dict[str, Any]] = []
        for trial, job in result.all():
            items.append(
                {
                    "id": trial.id,
                    "study_id": trial.study_id,
                    "trial_number": trial.trial_number,
                    "training_job_id": trial.training_job_id,
                    "params": trial.params,
                    "state": trial.state,
                    "value": trial.value,
                    "error_message": trial.error_message,
                    "created_at": trial.created_at,
                    "updated_at": trial.updated_at,
                    "job_name": job.name if job else None,
                    "job_status": job.status if job else None,
                }
            )
        return items

    async def get_best_trial(self, study_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
        """详情页 best: 实时查 Optuna (单一事实来源)."""
        study = await self._get_study_or_fail(study_id, tenant_id)
        best = await best_trial(study.optuna_study_name)
        if not best:
            return {"study_id": study_id, "trial_number": None, "training_job_id": None, "params": None, "value": None}
        trial = await self._get_trial_by_number(study.id, best["trial_number"])
        return {
            "study_id": study_id,
            "trial_number": best["trial_number"],
            "training_job_id": trial.training_job_id if trial else None,
            "params": best["params"],
            "value": best["value"],
        }

    async def get_insights(self, study_id: uuid.UUID, tenant_id: uuid.UUID) -> dict[str, Any]:
        """调优可视化数据: 优化历史 (Optuna 全量 trial) + 超参重要性.

        从 Optuna study 读取, 平台表不参与 — study 是优化状态的唯一事实来源,
        含运行中/失败/剪枝 trial 与时长, 天然与 ask/tell 同步.
        """
        study = await self._get_study_or_fail(study_id, tenant_id)
        optuna_study = await load_study(study.optuna_study_name)
        trials = await study_trials(optuna_study)

        history: list[dict[str, Any]] = []
        for t in trials:
            history.append(
                {
                    "trial_number": t.number,
                    "value": float(t.values[0]) if t.values else None,
                    "params": t.params,
                    "state": _map_trial_state(t.state),
                    "datetime_start": t.datetime_start,
                    "datetime_complete": t.datetime_complete,
                    "duration_seconds": t.duration.total_seconds() if t.duration else None,
                }
            )

        importance = await study_param_importances(optuna_study)
        return {"history": history, "importance": importance}

    # ── 停止 / 删除 ─────────────────────────────────────────────────
    async def stop_study(self, study_id: uuid.UUID, tenant_id: uuid.UUID) -> TuningStudy:
        study = await self._get_study_or_fail(study_id, tenant_id)
        if study.status != TuningStudyStatus.RUNNING.value:
            raise ConflictException(f"当前状态为 {study.status}, 无法停止")

        study.status = TuningStudyStatus.STOPPED.value
        # 停止所有可停止的 trial job (DB 状态 + K8s 删除由 Taskiq worker 异步执行).
        # 各 trial job 进入 STOPPED 后触发 finalize → reconcile 收尾并折算 best_value.
        await self._stop_trial_jobs(study.id, tenant_id)
        await self.db.commit()
        await self.db.refresh(study)
        return study

    async def delete_study(self, study_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        study = await self._get_study_or_fail(study_id, tenant_id)
        trials = await self._list_trials(study.id)

        # 仅终态 trial job 可删 (与训练任务删除语义一致): 先停止再删除.
        non_terminal = [t for t in trials if t.training_job_id and not await self._job_is_terminal(t.training_job_id)]
        if non_terminal:
            raise ConflictException("存在运行中的 trial 任务, 请先停止调优任务")

        for trial in trials:
            if trial.training_job_id is None:
                continue
            vcjob_name, namespace, tb, mlflow_exp = await self.training_service.delete_training_job_record(
                trial.training_job_id, tenant_id
            )
            from app.tasks.training_job_tasks import enqueue_delete_training_job

            await enqueue_delete_training_job(
                trial.training_job_id,
                vcjob_name,
                namespace,
                tensorboard_enabled=tb,
                mlflow_experiment_id=mlflow_exp,
            )

        await optuna_delete_study(study.optuna_study_name)
        await self.db.delete(study)
        await self.db.commit()

    # ── 驱动核心 ─────────────────────────────────────────────────────
    async def drive_study(self, study: TuningStudy) -> None:
        """单个 study 的一次驱动.

        顶层 setup 异常 (study 被删 / search_space 损坏) → mark FAILED (永久错误);
        循环内单点异常 → per-trial/per-step 隔离 (log + continue, study 保持 RUNNING).
        RUNNING: reconcile → prune(若启用) → 完成判定 → 补发.
        STOPPED/COMPLETED: 仅 reconcile (收尾残留 trial, 避免 Optuna 僵尸 RUNNING).
        """
        try:
            optuna_study = await load_study(study.optuna_study_name)
            distributions, fixed_params = json_search_space_to_distributions(study.search_space)
        except Exception as exc:
            logger.exception("tuning_drive_setup_error", extra={"study_id": str(study.id)})
            await self.mark_study_failed(study.id, f"驱动初始化失败: {exc}")
            return

        trials = await study_trials(optuna_study)
        still_running = await self._reconcile_trials(study, optuna_study, trials)

        if study.status != TuningStudyStatus.RUNNING.value:
            return

        if study.pruning_enabled:
            await self._prune_running_trials(study, optuna_study, trials)

        await self._check_completion(study, len(trials), still_running)
        if study.status == TuningStudyStatus.RUNNING.value:
            await self._spawn_trials(study, optuna_study, distributions, fixed_params, len(trials))

    async def mark_study_failed(self, study_id: uuid.UUID, error: str) -> None:
        result = await self.db.execute(select(TuningStudy).where(TuningStudy.id == study_id))
        study = result.scalar_one_or_none()
        if study is None or study.status != TuningStudyStatus.RUNNING.value:
            return
        study.status = TuningStudyStatus.FAILED.value
        study.error_message = error
        await self.db.commit()

    # ── reconcile: 同步平台表 + 幂等 tell + 孤儿回收 ──────────────────
    async def _reconcile_trials(
        self,
        study: TuningStudy,
        optuna_study: Any,
        trials: list[Any],
    ) -> int:
        """单次遍历 Optuna trials, 返回处理后仍 RUNNING 的 trial 数 (完成判定用).

        - Optuna 已终态 → 平台表过期则同步 state/value (不 tell)
        - Optuna RUNNING/WAITING → 看关联 job 决定 tell / 跳过(grace 内) / 留给 prune
        per-trial 异常隔离 (log + continue).
        """
        platform_trials = await self._load_platform_trial_map(study.id)
        job_ids = [t.training_job_id for t in platform_trials.values() if t.training_job_id]
        jobs = await self._load_jobs_map(job_ids)

        still_running = 0
        completed_values: list[float] = []
        dirty = False

        for t in trials:
            try:
                platform_trial = platform_trials.get(t.number)
                if t.state in _OPTUNA_FINISHED_STATES:
                    if t.state == TrialState.COMPLETE and t.values:
                        completed_values.append(float(t.values[0]))
                    if platform_trial is not None:
                        state = _map_trial_state(t.state)
                        value = float(t.values[0]) if t.values else None
                        if platform_trial.state != state or platform_trial.value != value:
                            platform_trial.state = state
                            platform_trial.value = value
                            dirty = True
                    continue

                # RUNNING / WAITING: 未 tell
                still_running += 1
                action, value = await self._resolve_running_trial(study, optuna_study, t, platform_trial, jobs)
                if action == "skip":
                    continue
                still_running -= 1
                dirty = True
                if action == "complete" and value is not None:
                    completed_values.append(value)
            except Exception:
                logger.exception("tuning_reconcile_trial_error", extra={"study_id": str(study.id), "trial": t.number})

        best = self._compute_best_value(study.direction, completed_values)
        if study.best_value != best:
            study.best_value = best
            dirty = True

        if dirty:
            await self.db.commit()
        return still_running

    async def _resolve_running_trial(
        self,
        study: TuningStudy,
        optuna_study: Any,
        frozen_trial: Any,
        platform_trial: TuningTrial | None,
        jobs: dict[uuid.UUID, TrainingJob],
    ) -> tuple[str, float | None]:
        """决定一个 Optuna 未终态 trial 的归宿, 返回 (action, value).

        action: "skip" 留到下 tick (metric 暂不可读 / job 仍运行); "complete"/"fail" 已 tell.
        """
        if platform_trial is None or platform_trial.training_job_id is None:
            await study_tell(optuna_study, frozen_trial.number, None)
            return "fail", None
        job = jobs.get(platform_trial.training_job_id)
        if job is None:
            await study_tell(optuna_study, frozen_trial.number, None)
            platform_trial.state = TuningTrialState.FAILED.value
            platform_trial.error_message = "trial 训练任务已被删除"
            return "fail", None

        if job.status not in TERMINAL_JOB_STATUSES:
            return "skip", None  # 仍运行, 留给 prune

        if job.status == TrainingJobStatus.SUCCEEDED:
            value = await self._read_metric_from_job(job, study.metric_name)
            if value is not None:
                await study_tell(optuna_study, frozen_trial.number, value)
                platform_trial.state = TuningTrialState.COMPLETE.value
                platform_trial.value = value
                platform_trial.error_message = None
                return "complete", value
            # metric 暂不可读: grace 内跳过 (下 tick 重试), 超时判 FAIL.
            if _within_metric_grace(job):
                return "skip", None
            await study_tell(optuna_study, frozen_trial.number, None)
            platform_trial.state = TuningTrialState.FAILED.value
            platform_trial.error_message = f"训练成功但未上报目标指标 {study.metric_name}"
            return "fail", None

        # FAILED / STOPPED
        await study_tell(optuna_study, frozen_trial.number, None)
        platform_trial.state = TuningTrialState.FAILED.value
        platform_trial.error_message = job.error_message or f"训练任务 {job.status}"
        return "fail", None

    async def _read_metric_series(self, job: TrainingJob, metric_name: str) -> list[tuple[int, float]]:
        """读 trial job 绑定 MLflow run 的 metric 完整序列, 按 step 升序返回 (step, value)."""
        result = await self.db.execute(select(Experiment.mlflow_run_id).where(Experiment.training_job_id == job.id))
        run_id = result.scalar_one_or_none()
        if not run_id:
            return []
        history = await get_mlflow_client().get_metric_history(run_id=run_id, metric_key=metric_name)
        points = [(int(h["step"]), float(h["value"])) for h in history if not h.get("is_nan")]
        points.sort(key=lambda p: p[0])
        return points

    async def _read_metric_from_job(self, job: TrainingJob, metric_name: str) -> float | None:
        """读最新 step 的 metric 值 (终态判定用; pruning 用完整序列 _read_metric_series)."""
        series = await self._read_metric_series(job, metric_name)
        return series[-1][1] if series else None

    @staticmethod
    def _compute_best_value(direction: str, values: list[float]) -> float | None:
        if not values:
            return None
        return min(values) if direction == "minimize" else max(values)

    async def _check_completion(self, study: TuningStudy, asked: int, still_running: int) -> None:
        """已 ask ≥ n_trials 且无运行中 trial → COMPLETED (best_value 已在 reconcile 折算)."""
        if asked >= study.n_trials and still_running == 0:
            study.status = TuningStudyStatus.COMPLETED.value
            await self.db.commit()

    # ── prune: 阈值剪枝 (默认关闭) ───────────────────────────────────
    async def _prune_running_trials(
        self,
        study: TuningStudy,
        optuna_study: Any,
        trials: list[Any],
    ) -> None:
        """阈值剪枝: 对运行中 trial 读 MLflow intermediate, 与已完成 trial 终值的中位数比较,
        差于中位数则 tell PRUNED + 停 job. 仅在 study.pruning_enabled 时由 drive_study 调用."""
        config = study.pruning_config or {}
        n_startup = int(config.get("n_startup_trials", 5))
        n_warmup = int(config.get("n_warmup_steps", 3))
        interval = int(config.get("interval", 1))
        n_min = int(config.get("n_min_trials", 3))

        completed_values = await self._completed_values(study.id)
        if len(completed_values) < max(n_startup, n_min):
            return  # 参考样本不足, 不剪
        threshold = _median(completed_values)
        minimize = study.direction == "minimize"

        for t in trials:
            if t.state != TrialState.RUNNING:
                continue
            try:
                platform_trial = await self._get_trial_by_number(study.id, t.number)
                if platform_trial is None or platform_trial.training_job_id is None:
                    continue
                job = await self._get_job(platform_trial.training_job_id)
                if job is None or job.status in _TERMINAL_STATUS_VALUES:
                    continue  # job 已终态/已删, 交给 reconcile
                series = await self._read_metric_series(job, study.metric_name)
                if not series:
                    continue
                latest_step, latest_value = series[-1]
                if latest_step < n_warmup or (interval > 0 and latest_step % interval != 0):
                    continue
                if latest_value > threshold if minimize else latest_value < threshold:
                    await study_tell(optuna_study, t.number, state=TrialState.PRUNED)
                    platform_trial.state = TuningTrialState.PRUNED.value
                    await self._stop_trial_job(platform_trial.training_job_id, study.tenant_id)
            except Exception:
                logger.exception("tuning_prune_trial_error", extra={"study_id": str(study.id), "trial": t.number})
        await self.db.commit()

    async def _completed_values(self, study_id: uuid.UUID) -> list[float]:
        result = await self.db.execute(
            select(TuningTrial.value).where(
                TuningTrial.study_id == study_id, TuningTrial.state == TuningTrialState.COMPLETE.value
            )
        )
        return [v for v in result.scalars().all() if v is not None]

    # ── spawn: 补发新 trial ──────────────────────────────────────────
    async def _spawn_trials(
        self,
        study: TuningStudy,
        optuna_study: Any,
        distributions: dict[str, Any],
        fixed_params: dict[str, Any],
        asked: int,
    ) -> None:
        """补发新 trial 直到达 n_trials 总数或 n_jobs 并发上限.

        asked = Optuna 已创建 trial 数 (len(get_trials)); running = 关联 job 非终态的行数.
        GPU 配额不足时停止补发, 下个 tick 重试 (不消耗 trial).
        单轮补发 (建 job/trial 行 + 入队) 任一步失败 → 回滚本次并停止补发 (下个 tick 重试),
        避免 enqueue 失败留下 PENDING 孤儿 trial 永久占用 n_jobs 槽位导致 study 卡死.
        """
        running = await self._count_running_trials(study.id)
        requested_gpu = study.gpu_count * study.worker_count

        while asked < study.n_trials and running < study.n_jobs:
            try:
                await self.training_service.check_gpu_quota_for_tenant(study.tenant_id, requested_gpu)
            except QuotaExceededException:
                logger.info("trial_gpu_quota_exceeded", extra={"study_id": str(study.id)})
                break

            trial = await study_ask(optuna_study, distributions)
            params = {**trial.params, **fixed_params}
            job: TrainingJob | None = None
            try:
                job = await self._create_trial_job(study, trial.number, params)
                self.db.add(
                    TuningTrial(
                        study_id=study.id,
                        trial_number=trial.number,
                        training_job_id=job.id,
                        params=params,
                        state=TuningTrialState.PENDING.value,
                    )
                )
                await self.db.commit()

                from app.tasks.training_job_tasks import enqueue_submit_training_job

                await enqueue_submit_training_job(job.id, study.tenant_id)
            except Exception:
                logger.exception(
                    "tuning_spawn_trial_error",
                    extra={"study_id": str(study.id), "trial_number": trial.number},
                )
                await self.db.rollback()
                await self._abort_trial_spawn(optuna_study, trial.number, job.id if job else None)
                break
            asked += 1
            running += 1

    async def _abort_trial_spawn(
        self,
        optuna_study: Any,
        trial_number: int,
        job_id: uuid.UUID | None,
    ) -> None:
        """回滚一次失败的 trial 补发 (best-effort): 删除未提交的 PENDING job + 关联 trial 行,
        并 tell Optuna FAIL 释放该 trial 占用的槽位.

        job 行由 create_training_job_record 内部已 commit, rollback 无法撤销, 故显式删除;
        仅删 vcjob_name 为空 (从未提交到 K8s) 的 job, 避免误删已提交资源. 全程不再上抛.
        """
        try:
            if job_id is not None:
                linked = await self.db.execute(select(TuningTrial).where(TuningTrial.training_job_id == job_id))
                for t in linked.scalars().all():
                    await self.db.delete(t)
                job = await self.db.get(TrainingJob, job_id)
                if job is not None and job.vcjob_name is None:
                    await self.db.delete(job)
            await self.db.commit()
        except Exception:
            logger.exception("tuning_abort_spawn_error", extra={"job_id": str(job_id) if job_id else None})
            with contextlib.suppress(Exception):
                await self.db.rollback()
        with contextlib.suppress(Exception):
            await study_tell(optuna_study, trial_number, None)

    async def _create_trial_job(self, study: TuningStudy, trial_number: int, params: dict[str, Any]) -> TrainingJob:
        """创建 trial 的 TrainingJob (source='tuning', 强制 mlflow 绑定)."""
        # 加入 study id 短哈希: TrainingJob 有 (tenant_id, name) 唯一约束, 仅靠 name[:40]
        # 会在两个前 40 字符相同的 study 间产生同名 trial job → IntegrityError.
        job_name = f"{study.name[:40]}-{study.id.hex[:8]}-trial-{trial_number}"
        return await self.training_service.create_training_job_record(
            tenant_id=study.tenant_id,
            user_id=study.created_by,
            name=job_name,
            image_id=study.image_id,
            command=study.command,
            description=study.description,
            dataset_id=study.dataset_id,
            dataset_version_id=study.dataset_version_id,
            hyperparameters=[{"key": k, "value": str(v)} for k, v in params.items()],
            env_vars=study.env_vars,
            gpu_count=study.gpu_count,
            gpu_mode=study.gpu_mode,
            cpu=study.cpu,
            memory=study.memory,
            priority=study.priority,
            worker_count=study.worker_count,
            source="tuning",
            mlflow_enabled=True,
            tensorboard_enabled=False,
        )

    # ── 内部: 停止 / 查询 ────────────────────────────────────────────
    async def _stop_trial_jobs(self, study_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(TuningTrial, TrainingJob)
            .join(TrainingJob, TuningTrial.training_job_id == TrainingJob.id)
            .where(
                TuningTrial.study_id == study_id,
                TrainingJob.status.in_(ALLOWED_STOP_STATUSES),
            )
        )
        from app.tasks.training_job_tasks import enqueue_stop_training_job

        for _, job in result.all():
            await self.training_service.stop_training_job_record(job.id, tenant_id)
            await enqueue_stop_training_job(job.id, tenant_id)

    async def _stop_trial_job(self, job_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """单个 trial job 停止 (prune 用): DB 置 STOPPED + 异步删 VCJob."""
        from app.tasks.training_job_tasks import enqueue_stop_training_job

        await self.training_service.stop_training_job_record(job_id, tenant_id)
        await enqueue_stop_training_job(job_id, tenant_id)

    async def _get_study_by_id(self, study_id: uuid.UUID) -> TuningStudy | None:
        result = await self.db.execute(select(TuningStudy).where(TuningStudy.id == study_id))
        return result.scalar_one_or_none()

    async def _get_study_or_fail(self, study_id: uuid.UUID, tenant_id: uuid.UUID) -> TuningStudy:
        result = await self.db.execute(
            select(TuningStudy).where(TuningStudy.id == study_id, TuningStudy.tenant_id == tenant_id)
        )
        study = result.scalar_one_or_none()
        if not study:
            raise NotFoundException("调优任务不存在")
        return study

    async def _list_trials(self, study_id: uuid.UUID) -> list[TuningTrial]:
        result = await self.db.execute(
            select(TuningTrial).where(TuningTrial.study_id == study_id).order_by(TuningTrial.trial_number.asc())
        )
        return list(result.scalars().all())

    async def _load_platform_trial_map(self, study_id: uuid.UUID) -> dict[int, TuningTrial]:
        result = await self.db.execute(select(TuningTrial).where(TuningTrial.study_id == study_id))
        return {t.trial_number: t for t in result.scalars().all()}

    async def _load_jobs_map(self, job_ids: list[uuid.UUID]) -> dict[uuid.UUID, TrainingJob]:
        if not job_ids:
            return {}
        result = await self.db.execute(select(TrainingJob).where(TrainingJob.id.in_(job_ids)))
        return {j.id: j for j in result.scalars().all()}

    async def _get_trial_by_number(self, study_id: uuid.UUID, trial_number: int) -> TuningTrial | None:
        result = await self.db.execute(
            select(TuningTrial).where(TuningTrial.study_id == study_id, TuningTrial.trial_number == trial_number)
        )
        return result.scalar_one_or_none()

    async def _get_job(self, job_id: uuid.UUID) -> TrainingJob | None:
        result = await self.db.execute(select(TrainingJob).where(TrainingJob.id == job_id))
        return result.scalar_one_or_none()

    async def _job_is_terminal(self, job_id: uuid.UUID) -> bool:
        result = await self.db.execute(select(TrainingJob.status).where(TrainingJob.id == job_id))
        status = result.scalar_one_or_none()
        return status in _TERMINAL_STATUS_VALUES

    async def _count_running_trials(self, study_id: uuid.UUID) -> int:
        """运行中 trial 数 = 关联 job 非终态的行数 (job 已删除的行不计入)."""
        result = await self.db.execute(
            select(func.count())
            .select_from(TuningTrial)
            .join(TrainingJob, TuningTrial.training_job_id == TrainingJob.id)
            .where(TuningTrial.study_id == study_id, TrainingJob.status.notin_(_TERMINAL_STATUS_VALUES))
        )
        return int(result.scalar_one())
