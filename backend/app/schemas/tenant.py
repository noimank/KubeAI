import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.enums import InvitationStatus, TenantStatus, UserRole


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


# --- Invitation Schemas ---


class InviteMemberRequest(BaseModel):
    email: EmailStr
    role: UserRole = Field(..., description="仅限 engineer/mlops/annotator")


class InvitationResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    role: UserRole
    token: str
    status: InvitationStatus
    invited_by: uuid.UUID
    expires_at: datetime
    created_at: datetime


class AcceptInvitationRequest(BaseModel):
    token: str = Field(..., min_length=1)
    username: str | None = Field(None, min_length=1, max_length=50)
    password: str | None = Field(None, min_length=8)
    confirm_password: str | None = None
    force: bool = False


class InvitationInfoResponse(BaseModel):
    tenant_name: str
    tenant_display_name: str
    email: str
    role: UserRole


# --- Member Schemas ---


class TenantMemberResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: UserRole
    is_active: bool
    joined_at: datetime


class UpdateMemberRoleRequest(BaseModel):
    role: UserRole = Field(..., description="仅限 engineer/mlops/annotator")


class AddMemberRequest(BaseModel):
    user_id: uuid.UUID
    role: UserRole = Field(..., description="仅限 engineer/mlops/annotator")
