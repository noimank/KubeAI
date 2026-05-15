from __future__ import annotations

import uuid

from sqlalchemy import JSON, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class InferenceService(Base, TimestampMixin):
    __tablename__ = "inference_services"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_inference_svc_tenant_name"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="租户 ID",
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        comment="创建者 ID",
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, comment="服务名称")
    model_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("model_versions.id", ondelete="RESTRICT"),
        nullable=False,
        comment="模型版本 ID",
    )
    image: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="推理镜像")
    gpu_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="GPU 数量")
    cpu: Mapped[str] = mapped_column(String(20), nullable=False, default="2", comment="CPU 核数")
    memory: Mapped[str] = mapped_column(String(20), nullable=False, default="4Gi", comment="内存")
    replicas: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="副本数")
    min_replicas: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="最小副本数")
    max_replicas: Mapped[int] = mapped_column(Integer, nullable=False, default=1, comment="最大副本数")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", comment="服务状态")
    kserve_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="KServe 资源名")
    endpoint_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="推理端点 URL")
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="描述")
    env_vars: Mapped[dict[str, str] | None] = mapped_column(JSON, nullable=True, comment="环境变量")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="错误信息")
    auth_token_hash: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True, comment="API Token 哈希"
    )
    proxy_endpoint: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="代理端点 URL")

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("id", uuid.uuid4())
        super().__init__(**kwargs)
