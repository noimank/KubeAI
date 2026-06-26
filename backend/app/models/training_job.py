from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TrainingJob(Base, TimestampMixin):
    __tablename__ = "training_jobs"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_training_job_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="租户 ID",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="任务名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="任务描述")
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="创建者 ID",
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
    image_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("images.id", ondelete="RESTRICT"),
        nullable=False,
        comment="镜像 ID",
    )

    command: Mapped[str] = mapped_column(Text, nullable=False, comment="启动命令")
    hyperparameters: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True, comment="超参数")

    gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="GPU 数量")
    gpu_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="exclusive", comment="GPU 模式")
    cpu: Mapped[str] = mapped_column(String(20), nullable=False, default="4", comment="CPU 核数")
    memory: Mapped[str] = mapped_column(String(20), nullable=False, default="8Gi", comment="内存")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal", comment="优先级")
    worker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="Worker 数量")

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", comment="任务状态")
    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="manual",
        comment="任务来源: manual=手动创建, dev_environment=开发环境, experiment_reproduction=实验复现",
    )
    source_env_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("dev_environments.id", ondelete="SET NULL"),
        nullable=True,
        comment="来源开发环境 ID",
    )
    vcjob_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="Volcano Job 名称")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="开始时间")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="结束时间")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")

    mlflow_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否启用 MLflow 实验追踪 (默认关闭, 需要可视化时在创建表单中开启)",
    )
    tensorboard_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default="false",
        comment="是否启用 TensorBoard 可视化 (默认关闭, 平台注入 sidecar 自动读取 tfevents)",
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
