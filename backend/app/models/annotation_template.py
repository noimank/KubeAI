from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.annotation import AnnotationProject


class AnnotationTemplate(Base, TimestampMixin, TenantMixin):
    """租户级标注模板 — 创建项目时拍快照, 后续编辑不影响已建项目."""

    __tablename__ = "annotation_templates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_annotation_templates_tenant_name"),
        Index(
            "ix_annotation_templates_tags",
            "tags",
            postgresql_using="gin",
            postgresql_ops={"tags": "jsonb_path_ops"},
        ),
        Index("ix_annotation_templates_group", "group"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    label_config: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    group: Mapped[str] = mapped_column(String(100), nullable=False, default="其他")

    projects: Mapped[list[AnnotationProject]] = relationship(back_populates="template", lazy="noload")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("group", "其他")
        kwargs.setdefault("tags", [])
        super().__init__(**kwargs)
