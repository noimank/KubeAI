from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.annotation_task import AnnotationTask
    from app.models.dataset import Dataset, DatasetVersion


class AnnotationProject(Base, TimestampMixin, TenantMixin):
    __tablename__ = "annotation_projects"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_annotation_project_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id"), nullable=False)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_versions.id"), nullable=False)
    annotation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    label_studio_project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label_config: Mapped[str] = mapped_column(Text, nullable=False)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    dataset: Mapped[Dataset] = relationship(lazy="selectin")
    dataset_version: Mapped[DatasetVersion] = relationship(lazy="selectin", foreign_keys=[dataset_version_id])
    tasks: Mapped[list[AnnotationTask]] = relationship(back_populates="project", lazy="noload")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
