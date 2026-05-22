from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class DevEnvironmentImage(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "dev_environment_images"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", "environment_type", name="uq_dev_env_img_tenant_name_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="环境镜像名称")
    environment_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="环境类型: jupyter/vscode/rstudio"
    )
    image_ref: Mapped[str] = mapped_column(String(500), nullable=False, comment="完整容器镜像地址")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="图标标识")
    default_cpu: Mapped[str] = mapped_column(String(20), nullable=False, default="2", comment="默认 CPU 核数")
    default_memory: Mapped[str] = mapped_column(String(20), nullable=False, default="4Gi", comment="默认内存")
    default_gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="默认 GPU 数量")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True, comment="租户 ID, null 表示平台级"
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
