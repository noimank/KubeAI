import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import TenantStatus


class TenantCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    display_name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class TenantUpdateRequest(BaseModel):
    display_name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None


class TenantStatusRequest(BaseModel):
    status: TenantStatus


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    display_name: str
    description: str | None = None
    status: TenantStatus
    k8s_namespace_name: str | None = None
    gpu_limit: int
    cpu_limit: str
    memory_limit: str
    storage_limit: str
    member_count: int = 0
    created_at: datetime
    updated_at: datetime


class TenantDetailResponse(TenantResponse):
    pass
