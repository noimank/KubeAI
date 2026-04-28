import uuid

from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import String, Text
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

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("status", TenantStatus.ACTIVE)
        super().__init__(**kwargs)
