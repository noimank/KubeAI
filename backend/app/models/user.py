import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, SoftDeleteMixin, TimestampMixin
from app.models.enums import UserRole


class User(Base, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    role: Mapped[UserRole] = mapped_column(
        SQLAlchemyEnum(UserRole, values_callable=lambda e: [x.value for x in e]),
        default=UserRole.ENGINEER,
        server_default="engineer",
        nullable=False,
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("id", uuid.uuid4())
        kwargs.setdefault("is_active", True)
        kwargs.setdefault("failed_login_attempts", 0)
        kwargs.setdefault("role", UserRole.ENGINEER)
        super().__init__(**kwargs)
