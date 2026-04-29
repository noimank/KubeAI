import uuid

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import TenantStatus


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TenantStatus] = mapped_column(
        SQLAlchemyEnum(TenantStatus, values_callable=lambda e: [x.value for x in e]),
        default=TenantStatus.ACTIVE,
        server_default="active",
        nullable=False,
    )
    k8s_namespace_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gpu_limit: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    cpu_limit: Mapped[str] = mapped_column(String(20), default="4", server_default="4", nullable=False)
    memory_limit: Mapped[str] = mapped_column(String(20), default="8Gi", server_default="8Gi", nullable=False)
    storage_limit: Mapped[str] = mapped_column(String(20), default="10Gi", server_default="10Gi", nullable=False)

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("status", TenantStatus.ACTIVE)
        super().__init__(**kwargs)
