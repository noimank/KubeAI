import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.enums import UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: UserRole
    is_active: bool
    auth_provider: str = "local"
    tenant_id: uuid.UUID | None = None
    tenant_name: str | None = None
    created_at: datetime
    updated_at: datetime


class UserDetailResponse(UserResponse):
    failed_login_attempts: int = 0
    locked_until: datetime | None = None


class UserUpdateRequest(BaseModel):
    role: UserRole | None = None
    tenant_id: uuid.UUID | None = None


class UserStatusToggleRequest(BaseModel):
    is_active: bool
