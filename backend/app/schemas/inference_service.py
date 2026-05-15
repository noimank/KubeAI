import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class InferenceServiceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    model_version_id: uuid.UUID
    gpu_count: int = Field(default=0, ge=0)
    cpu: str = Field(default="2")
    memory: str = Field(default="4Gi")
    replicas: int = Field(default=1, ge=1)
    image: str | None = None
    env_vars: dict[str, str] | None = None
    description: str | None = None


class ModelVersionSummary(BaseModel):
    id: uuid.UUID
    version_number: int
    registered_model_id: uuid.UUID
    status: str


class InferenceServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    name: str
    model_version_id: uuid.UUID
    image: str | None
    gpu_count: int
    cpu: str
    memory: str
    replicas: int
    min_replicas: int
    max_replicas: int
    status: str
    kserve_name: str | None
    endpoint_url: str | None
    proxy_endpoint: str | None
    has_token: bool = False
    description: str | None
    env_vars: dict[str, str] | None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    model_version: ModelVersionSummary | None = None


class InferenceServiceListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: str | None = None
    name: str | None = None


class TokenRegenerateResponse(BaseModel):
    token: str
    message: str


class InferenceServiceCreateResponse(InferenceServiceResponse):
    auth_token: str


class InferenceServiceScaleRequest(BaseModel):
    replicas: int = Field(..., ge=0, le=100, description="目标副本数")


class InferenceServiceScaleResponse(InferenceServiceResponse):
    pass


class InferenceServiceEventResponse(BaseModel):
    type: str
    reason: str
    message: str
    involved_object_kind: str
    involved_object_name: str
    count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
