import uuid

from sqlalchemy import BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantMixin, TimestampMixin


class Algorithm(Base, TimestampMixin, TenantMixin):
    __tablename__ = "algorithms"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_algorithms_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    storage_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="available")
    visibility: Mapped[str] = mapped_column(String(20), nullable=False, default="tenant")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("source_type", "upload")
        kwargs.setdefault("status", "available")
        kwargs.setdefault("visibility", "tenant")
        kwargs.setdefault("tags", [])
        super().__init__(**kwargs)
