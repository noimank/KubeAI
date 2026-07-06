from __future__ import annotations

import uuid

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin
from app.models.enums import ModelVersionStatus


class RegisteredModel(Base, TimestampMixin, TenantMixin):
    __tablename__ = "registered_models"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_model_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    versions: Mapped[list[ModelVersion]] = relationship(
        back_populates="model", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)


class ModelVersion(Base, TimestampMixin):
    __tablename__ = "model_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    registered_model_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("registered_models.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=ModelVersionStatus.UPLOADING, nullable=False)
    upload_job_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    training_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("training_jobs.id", ondelete="SET NULL"), nullable=True
    )
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("datasets.id"), nullable=True)
    dataset_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("dataset_versions.id"), nullable=True)
    image_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("images.id"), nullable=True)
    hyperparameters: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    model: Mapped[RegisteredModel] = relationship(back_populates="versions", lazy="joined")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
