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


class TenantQuotaUpdateRequest(BaseModel):
    gpu_limit: int = Field(..., ge=0)
    cpu_limit: str = Field(..., pattern=r"^\d+(\.\d+)?m?$")
    memory_limit: str = Field(..., pattern=r"^\d+(\.\d+)?(Ki|Mi|Gi|Ti)?$")
    storage_limit: str = Field(..., pattern=r"^\d+(\.\d+)?(Ki|Mi|Gi|Ti)?$")
    force: bool = False


class QuotaUsageResponse(BaseModel):
    gpu_used: int = 0
    cpu_used: str = "0"
    memory_used: str = "0"
    storage_used: str = "0"


class TenantDetailResponse(TenantResponse):
    pass
