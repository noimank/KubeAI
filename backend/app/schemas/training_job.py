import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HyperparameterItem(BaseModel):
    key: str
    value: str


class TrainingJobCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    dataset_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    image_id: uuid.UUID
    command: str = Field(..., min_length=1)
    hyperparameters: list[HyperparameterItem] | None = None
    gpu_count: int = Field(default=1, ge=0)
    gpu_mode: str = Field(default="exclusive", pattern="^(exclusive|shared)$")
    cpu: str = Field(default="4")
    memory: str = Field(default="8Gi")
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")


class TrainingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    dataset_id: uuid.UUID | None
    dataset_version_id: uuid.UUID | None
    image_id: uuid.UUID
    command: str
    hyperparameters: dict[str, str] | None
    gpu_count: int
    gpu_mode: str
    cpu: str
    memory: str
    priority: str
    status: str
    vcjob_name: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class TrainingJobListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: str | None = None
    name: str | None = None
