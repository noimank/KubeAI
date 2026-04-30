import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AuditAction, ResourceType


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID | None = None
    username: str | None = None
    tenant_id: uuid.UUID | None = None
    action: str
    resource_type: str
    resource_id: str | None = None
    detail: dict[str, Any] | None = None
    ip_address: str
    user_agent: str | None = None
    request_id: str | None = None
    created_at: datetime


class AuditLogQueryParams(BaseModel):
    action: list[AuditAction] | None = None
    resource_type: list[ResourceType] | None = None
    username: str | None = None
    user_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
