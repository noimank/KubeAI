from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class TuningStudy(Base, TimestampMixin, TenantMixin):
    """自动超参调优任务 (Optuna study 的平台侧快照).

    训练模板在此冻结 (镜像/数据集/命令/资源), 创建后修改不影响已产生的 trial.
    目标指标 metric_name 由调度器从每个 trial 绑定的 MLflow run 读取.
    """

    __tablename__ = "tuning_studies"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_tuning_studies_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="调优任务名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="创建者 ID",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        comment="调优状态: running/completed/stopped/failed",
    )
    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="minimize",
        comment="优化方向: minimize/maximize",
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="目标指标名称 (MLflow metric key)")
    n_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=10, comment="试验总数")
    n_jobs: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="并发试验上限")
    search_space: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, comment="搜索空间定义")

    # ── 训练模板快照 ─────────────────────────────────────────────
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="RESTRICT"),
        nullable=False,
        comment="镜像 ID",
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("datasets.id", ondelete="RESTRICT"),
        nullable=True,
        comment="数据集 ID",
    )
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="RESTRICT"),
        nullable=True,
        comment="数据集版本 ID",
    )
    command: Mapped[str] = mapped_column(Text, nullable=False, comment="训练命令")
    gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="GPU 数量")
    gpu_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="exclusive", comment="GPU 模式")
    cpu: Mapped[str] = mapped_column(String(20), nullable=False, default="4", comment="CPU 核数")
    memory: Mapped[str] = mapped_column(String(20), nullable=False, default="8Gi", comment="内存")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal", comment="优先级")
    worker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="Worker 数量")
    env_vars: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True, comment="附加到每个 trial 的环境变量")

    # ── Optuna 链接 ──────────────────────────────────────────────
    optuna_study_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        comment="Optuna study 名称 (唯一, 对应 RDBStorage 中的 study)",
    )

    # ── 最佳结果 (reconcile 时按 direction 折算 best_value; 详情页走 /best 实时查 Optuna) ──
    best_value: Mapped[float | None] = mapped_column(Float, nullable=True, comment="最佳指标值")

    # ── 剪枝 (pruning, 默认关闭) ─────────────────────────────────────
    pruning_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
        comment="是否启用剪枝",
    )
    pruning_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="剪枝配置")

    # ── 搜索策略 / 终止条件 (均可选, 为空走默认 TPE / 无额外终止) ───
    sampler_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="采样器配置")
    stopping_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="终止条件配置")

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)


class TuningTrial(Base, TimestampMixin):
    """单个 trial (一个独立 TrainingJob) 的平台侧执行记录.

    幂等以 Optuna trial state 为事实来源: reconcile 只对 Optuna 里 RUNNING/WAITING
    的 trial 调 tell, 已终态的跳过 tell 仅同步本表 state/value.
    """

    __tablename__ = "tuning_trials"
    __table_args__ = (
        UniqueConstraint("study_id", "trial_number", name="uq_tuning_trials_study_number"),
        UniqueConstraint("training_job_id", name="uq_tuning_trials_training_job"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    study_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tuning_studies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="调优任务 ID",
    )
    trial_number: Mapped[int] = mapped_column(Integer, nullable=False, comment="Optuna trial 序号")
    training_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="SET NULL"),
        nullable=True,
        comment="训练任务 ID (trial job 被单独删除时置空, 该 trial 由调度器记为 FAIL)",
    )
    params: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, comment="采样超参快照")
    state: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        comment="trial 状态: pending/running/complete/failed/pruned (与 Optuna trial state 同步)",
    )
    value: Mapped[float | None] = mapped_column(Float, nullable=True, comment="已上报的指标值")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
