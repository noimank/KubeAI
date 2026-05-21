import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DatasetMountRequest(BaseModel):
    dataset_id: uuid.UUID
    version_id: uuid.UUID | None = None


class DatasetMountInfo(BaseModel):
    dataset_id: uuid.UUID
    dataset_name: str
    version_id: uuid.UUID
    version_number: int
    mount_path: str


class DevEnvironmentCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    image: str = Field(..., min_length=1, max_length=500)
    gpu_count: int = Field(default=0, ge=0)
    cpu: str = Field(default="2")
    memory: str = Field(default="4Gi")
    description: str | None = None
    env_vars: dict[str, str] | None = None
    datasets: list[DatasetMountRequest] | None = None


class DevEnvironmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    name: str
    image: str
    gpu_count: int
    cpu: str
    memory: str
    status: str
    jupyterhub_user: str | None = None
    notebook_url: str | None = None
    pvc_name: str | None = None
    description: str | None = None
    env_vars: dict[str, str] | None = None
    error_message: str | None = None
    last_active_at: str | None = None
    stopped_reason: str | None = None
    mounted_datasets: list[DatasetMountInfo] | None = None
    created_at: datetime
    updated_at: datetime


class DevEnvironmentListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: str | None = None
    name: str | None = None


class NotebookUrlResponse(BaseModel):
    notebook_url: str
    message: str
