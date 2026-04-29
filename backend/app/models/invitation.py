from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import InvitationStatus, UserRole


class TenantInvitation(Base, TimestampMixin):
    __tablename__ = "tenant_invitations"
    __table_args__ = (
        Index(
            "uq_invitations_tenant_email_pending",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where="status = 'pending'",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        SQLAlchemyEnum(UserRole, values_callable=lambda e: [x.value for x in e]),
        default=UserRole.ENGINEER,
        server_default="engineer",
        nullable=False,
    )
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    status: Mapped[InvitationStatus] = mapped_column(
        SQLAlchemyEnum(InvitationStatus, values_callable=lambda e: [x.value for x in e]),
        default=InvitationStatus.PENDING,
        server_default="pending",
        nullable=False,
    )
    invited_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    accepted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("token", secrets.token_urlsafe(48))
        kwargs.setdefault("status", InvitationStatus.PENDING)
        if "expires_at" not in kwargs:
            kwargs["expires_at"] = datetime.now(UTC) + timedelta(days=7)
        super().__init__(**kwargs)
