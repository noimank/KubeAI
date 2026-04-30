import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class DatasetVersionCreateRequest(BaseModel):
    description: str | None = None


class DatasetVersionResponse(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_number: int
    description: str | None = None
    storage_path: str
    file_count: int
    total_size_bytes: int
    created_by: uuid.UUID
    created_at: datetime


class DatasetResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    created_by_name: str | None = None
    version_count: int = 0
    total_file_count: int = 0
    total_size_bytes: int = 0
    latest_version: DatasetVersionResponse | None = None
    created_at: datetime
    updated_at: datetime


class DatasetDetailResponse(DatasetResponse):
    versions: list[DatasetVersionResponse] = []


class FileUploadResponse(BaseModel):
    file_name: str
    object_name: str
    size_bytes: int
    content_type: str
