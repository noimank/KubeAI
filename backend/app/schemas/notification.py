import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import NotificationPriority, NotificationType


class NotificationResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    type: NotificationType
    title: str
    content: str
    priority: NotificationPriority
    is_read: bool
    resource_type: str | None = None
    resource_id: str | None = None
    created_at: datetime


class NotificationListQuery(BaseModel):
    type: NotificationType | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)


class UnreadCountResponse(BaseModel):
    count: int
