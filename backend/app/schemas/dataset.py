import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class DatasetCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    display_name: str | None = Field(None, max_length=200)
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
    display_name: str | None = None
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


class FileVersionFileResponse(BaseModel):
    file_name: str
    size_bytes: int = 0
    content_type: str = "application/octet-stream"
    last_modified: datetime | None = None


class FileTypeDistribution(BaseModel):
    extension: str
    count: int
    total_size_bytes: int


class VersionStatsResponse(BaseModel):
    version_id: uuid.UUID
    version_number: int
    file_count: int
    total_size_bytes: int
    file_type_distribution: list[FileTypeDistribution]


class FileDownloadRequest(BaseModel):
    file_name: str


class DatasetMountRequest(BaseModel):
    dataset_id: uuid.UUID
    version_id: uuid.UUID


class DatasetMountInfoResponse(BaseModel):
    pvc_name: str
    mount_path: str
    access_mode: str
    storage_request: str
    pvc_status: str


class InitContainerSyncInfo(BaseModel):
    minio_bucket: str
    minio_prefix: str
    pvc_mount_path: str
