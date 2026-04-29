from __future__ import annotations

import uuid
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, SoftDeleteMixin, TimestampMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.tenant import Tenant


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("auth_provider", "external_id", name="uq_users_auth_provider_external_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(20), default="local", server_default="local", nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SQLAlchemyEnum(UserRole, values_callable=lambda e: [x.value for x in e]),
        default=UserRole.ENGINEER,
        server_default="engineer",
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tenants.id"),
        nullable=True,
        index=True,
    )

    tenant: Mapped[Tenant | None] = relationship(backref="users", lazy="selectin", viewonly=True)

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("is_active", True)
        kwargs.setdefault("failed_login_attempts", 0)
        kwargs.setdefault("role", UserRole.ENGINEER)
        super().__init__(**kwargs)
