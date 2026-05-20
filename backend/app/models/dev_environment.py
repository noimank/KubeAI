from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class DevEnvironment(Base, TimestampMixin):
    __tablename__ = "dev_environments"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_dev_env_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True, comment="租户 ID"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="创建者 ID"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="环境名称")
    image: Mapped[str] = mapped_column(String(500), nullable=False, comment="镜像地址")
    gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="GPU 数量")
    cpu: Mapped[str] = mapped_column(String(20), nullable=False, default="2", comment="CPU 核数")
    memory: Mapped[str] = mapped_column(String(20), nullable=False, default="4Gi", comment="内存")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", comment="环境状态")
    jupyterhub_user: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="JupyterHub 用户名")
    notebook_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="Notebook URL")
    pvc_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="个人 PVC 名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    env_vars: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True, comment="环境变量")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    last_active_at: Mapped[str | None] = mapped_column(String(30), nullable=True, comment="上次活跃时间")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
