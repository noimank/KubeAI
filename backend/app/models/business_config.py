"""业务配置模型（环境变量预设）。"""

import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BusinessConfig(Base, TimestampMixin):
    __tablename__ = "business_configs"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_biz_cfg_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True, comment="租户 ID"
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, comment="创建者 ID"
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="配置名称")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    env_vars: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict, comment="环境变量键值对")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
