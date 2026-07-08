from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003  # SQLAlchemy resolves Mapped[] annotations at runtime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin


class Dataset(Base, TimestampMixin, TenantMixin):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_dataset_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    versions: Mapped[list[DatasetVersion]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)


class DatasetVersion(Base, TimestampMixin):
    __tablename__ = "dataset_versions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)

    dataset: Mapped[Dataset] = relationship(back_populates="versions")
    files: Mapped[list[DatasetFile]] = relationship(
        back_populates="version", cascade="all, delete-orphan", lazy="selectin"
    )

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)


class DatasetFile(Base, TenantMixin, TimestampMixin):
    """单个 dataset_version 下挂载的文件清单. DB 是 single source of truth."""

    __tablename__ = "dataset_files"
    __table_args__ = (
        UniqueConstraint("version_id", "relative_path", name="uq_dataset_file_version_path"),
        Index("ix_dataset_files_version_uploaded_at", "version_id", "uploaded_at"),
        Index("ix_dataset_files_version_name", "version_id", "file_name"),
        Index("ix_dataset_files_dataset", "dataset_id"),
        Index("ix_dataset_files_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    version_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    relative_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    version: Mapped[DatasetVersion] = relationship(back_populates="files")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
