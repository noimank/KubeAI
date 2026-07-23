"""数据库连接配置模型。"""

import enum
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class DbType(enum.StrEnum):
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SPARK = "spark"
    HIVE = "hive"
    MSSQL = "mssql"
    DORIS = "doris"


class DbConnection(Base, TimestampMixin, TenantMixin):
    """数据库连接配置，租户隔离，密码 Fernet 加密存储。"""

    __tablename__ = "db_connections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, comment="连接名称")
    db_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="数据库类型")
    host: Mapped[str] = mapped_column(String(500), nullable=False, comment="主机地址")
    port: Mapped[int] = mapped_column(nullable=False, comment="端口")
    database_name: Mapped[str] = mapped_column(String(200), nullable=False, comment="数据库名")
    username: Mapped[str] = mapped_column(String(200), nullable=False, comment="用户名")
    encrypted_password: Mapped[str] = mapped_column(Text, nullable=False, comment="Fernet 加密密码")
    extra_params: Mapped[str | None] = mapped_column(Text, nullable=True, comment="额外连接参数 JSON")
    description: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="备注")
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, comment="创建者"
    )

    # Relationships
    creator: Mapped["User"] = relationship("User", lazy="selectin", foreign_keys=[created_by])

    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_db_connections_tenant_name"),)

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
