import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SearchSpaceType = Literal["float", "int", "categorical", "fixed"]
SamplerType = Literal["tpe", "cmaes", "random"]


class SearchSpaceItem(BaseModel):
    """单个超参的搜索空间定义.

    按 ``type`` 取字段: float/int → low/high/log/step; categorical → choices; fixed → value.
    校验 (非法类型/区间/log+step 冲突) 由 optuna 构造 distributions 时完成, 创建接口兜底转译.
    """

    type: SearchSpaceType
    low: float | None = None
    high: float | None = None
    log: bool = False
    step: float | int | None = None
    choices: list[str] | None = None
    value: float | int | str | bool | None = None


class PruningConfig(BaseModel):
    """阈值剪枝配置 (pruning 默认关闭).

    参考分布用已完成 trial 终值在 ``prune_percentile`` 百分位处的值; 仅当完成数 ≥
    n_startup_trials 且当前 trial step ≥ n_warmup_steps 时评估, 每 interval 步评一次,
    参考样本 < n_min_trials 不判. 训练脚本须对 metric_name 按 step 上报
    (mlflow.log_metric(name, value, step=...)).
    """

    n_startup_trials: int = Field(default=5, ge=0, description="前 N 个 trial 不剪枝 (攒参考分布)")
    n_warmup_steps: int = Field(default=3, ge=0, description="每个 trial 前 N 步不评估")
    interval: int = Field(default=1, ge=1, description="每 N 步评估一次")
    n_min_trials: int = Field(default=3, ge=1, description="参考样本不足此数不判")
    prune_percentile: float = Field(default=50.0, ge=0.0, le=100.0, description="剪枝参考百分位(默认 50 = 中位数)")


class SamplerConfig(BaseModel):
    """采样器配置 (搜索策略). ``multivariate`` / ``n_startup_trials`` 仅对 TPE 生效.

    RDBStorage 不持久化 sampler, 创建与每次调度 tick 都由 ``build_sampler`` 从本配置重建.
    """

    type: SamplerType = "tpe"
    seed: int | None = Field(default=None, ge=0, description="随机种子")
    multivariate: bool = Field(default=False, description="仅 TPE: 多变量采样 (建模参数间相关)")
    n_startup_trials: int | None = Field(default=None, ge=0, description="仅 TPE: 前 N 个 trial 随机采样")


class StoppingConfig(BaseModel):
    """终止条件配置. 三者均可独立为空.

    study_timeout: 整个调优任务超时, 到点停止补发新 trial, 等运行中 trial 自然结束后置 COMPLETED.
    trial_timeout: 单个 trial 训练超时, 超时判 FAIL 并停止其训练任务 (需训练任务有 started_at).
    early_stop_patience: 连续 N 个已完成 trial 无改进后提前结束.
    """

    study_timeout_seconds: int | None = Field(default=None, ge=1, description="整个调优任务超时(秒)")
    trial_timeout_seconds: int | None = Field(default=None, ge=1, description="单个 trial 超时(秒)")
    early_stop_patience: int | None = Field(default=None, ge=1, description="连续 N 个无改进 trial 后提前结束")


class TuningStudyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    direction: Literal["minimize", "maximize"] = "minimize"
    metric_name: str = Field(min_length=1, max_length=100, description="目标指标名称 (MLflow metric key)")
    n_trials: int = Field(default=10, ge=1, le=1000, description="试验总数")
    n_jobs: int = Field(default=1, ge=1, le=16, description="并发试验上限")
    search_space: dict[str, SearchSpaceItem]
    image_id: uuid.UUID
    dataset_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    command: str = Field(min_length=1)
    gpu_count: int = Field(default=1, ge=0)
    gpu_mode: str = Field(default="exclusive", pattern="^(exclusive|shared)$")
    cpu: str = Field(default="4")
    memory: str = Field(default="8Gi")
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    worker_count: int = Field(default=1, ge=1, le=16)
    env_vars: dict[str, str] | None = None
    pruning_enabled: bool = False
    pruning_config: PruningConfig | None = None
    sampler_config: SamplerConfig | None = None
    stopping_config: StoppingConfig | None = None


class TuningStudyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    status: str
    direction: str
    metric_name: str
    n_trials: int
    n_jobs: int
    search_space: dict[str, Any]
    image_id: uuid.UUID
    dataset_id: uuid.UUID | None
    dataset_version_id: uuid.UUID | None
    command: str
    gpu_count: int
    gpu_mode: str
    cpu: str
    memory: str
    priority: str
    worker_count: int
    env_vars: dict[str, str] | None
    optuna_study_name: str
    best_value: float | None
    pruning_enabled: bool
    pruning_config: PruningConfig | None
    sampler_config: SamplerConfig | None
    stopping_config: StoppingConfig | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    # ── 进度统计 (由 service 注入, 非 DB 字段) ─────────────────────
    trial_count: int = 0
    finalized_count: int = 0
    running_count: int = 0


class TuningTrialResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    study_id: uuid.UUID
    trial_number: int
    training_job_id: uuid.UUID | None
    params: dict[str, Any] | None
    state: str
    value: float | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    # ── 关联训练任务信息 (由 service join 注入) ────────────────────
    job_name: str | None = None
    job_status: str | None = None
    experiment_id: uuid.UUID | None = None


class BestTrialResponse(BaseModel):
    study_id: uuid.UUID
    trial_number: int | None
    training_job_id: uuid.UUID | None
    params: dict[str, Any] | None
    value: float | None


class TuningTrialPoint(BaseModel):
    """insights 单个 trial 点 (来源: Optuna FrozenTrial)."""

    trial_number: int
    value: float | None = None
    params: dict[str, Any]
    state: str  # complete/failed/pruned/running/pending
    datetime_start: datetime | None = None
    datetime_complete: datetime | None = None
    duration_seconds: float | None = None


class TuningInsightsResponse(BaseModel):
    """调优可视化数据: 优化历史 + 超参重要性."""

    history: list[TuningTrialPoint]
    importance: dict[str, float]
