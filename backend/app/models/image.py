from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin


class Image(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "images"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="镜像名称")
    tag: Mapped[str] = mapped_column(String(100), nullable=False, comment="镜像标签/版本")
    image_ref: Mapped[str] = mapped_column(String(500), nullable=False, comment="完整镜像地址")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="镜像描述")
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="preset", comment="来源")
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, comment="是否启用")

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="tenant id, null for platform-level preset images",
    )
    build_status: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        default=None,
        comment="build status: pending/building/pushing/succeeded/failed, null for preset images",
    )
    dockerfile: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        default=None,
        comment="dockerfile content, only for custom images",
    )
    build_job_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        default=None,
        comment="k8s job name for tracking build status",
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
