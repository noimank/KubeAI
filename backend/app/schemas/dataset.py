import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from app.models.dataset import DatasetFile


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


SortBy = Literal["file_name", "file_size", "uploaded_at"]
SortDir = Literal["asc", "desc"]


class VersionFileResponse(BaseModel):
    file_id: uuid.UUID
    file_name: str
    relative_path: str
    file_size: int = 0
    content_type: str | None = None
    uploaded_at: datetime
    is_annotated: bool = False

    @classmethod
    def from_orm_file(cls, file: "DatasetFile", *, is_annotated: bool = False) -> "VersionFileResponse":
        return cls(
            file_id=file.id,
            file_name=file.file_name,
            relative_path=file.relative_path,
            file_size=file.file_size,
            content_type=file.content_type,
            uploaded_at=file.uploaded_at,
            is_annotated=is_annotated,
        )


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
    annotated_count: int = 0


class FileDownloadRequest(BaseModel):
    file_name: str


class DatasetMountRequest(BaseModel):
    dataset_id: uuid.UUID
    version_id: uuid.UUID
