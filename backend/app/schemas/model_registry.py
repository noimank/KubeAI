import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelVersionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    file_paths: list[str] = Field(..., min_length=1)
    training_job_id: uuid.UUID | None = None


class ModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registered_model_id: uuid.UUID
    version_number: int
    description: str | None = None
    storage_path: str
    file_count: int
    total_size_bytes: int
    training_job_id: uuid.UUID | None = None
    dataset_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    image_id: uuid.UUID | None = None
    hyperparameters: dict[str, str] | None = None
    created_by: uuid.UUID
    created_at: datetime


class RegisteredModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    created_by_name: str | None = None
    version_count: int = 0
    latest_version: ModelVersionResponse | None = None
    created_at: datetime
    updated_at: datetime


class RegisteredModelDetailResponse(RegisteredModelResponse):
    versions: list[ModelVersionResponse] = []
