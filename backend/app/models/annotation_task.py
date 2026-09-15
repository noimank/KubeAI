from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.annotation import AnnotationProject
    from app.models.user import User


class AnnotationTask(Base, TimestampMixin, TenantMixin):
    __tablename__ = "annotation_tasks"
    __table_args__ = (
        Index("idx_annotation_tasks_project", "project_id"),
        Index("idx_annotation_tasks_assigned_to", "assigned_to"),
        Index("idx_annotation_tasks_tenant_status", "tenant_id", "status"),
        UniqueConstraint("project_id", "kubeai_object_name", name="uq_annotation_task_project_object"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("annotation_projects.id", ondelete="CASCADE"), nullable=False
    )
    kubeai_object_name: Mapped[str] = mapped_column(String(1024), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="unassigned")

    project: Mapped[AnnotationProject] = relationship(back_populates="tasks", lazy="selectin")
    assignee: Mapped[User | None] = relationship(lazy="selectin")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
