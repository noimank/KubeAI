import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.enums import BuildStatus


class ImageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    tag: str = Field(..., min_length=1, max_length=100)
    image_ref: str = Field(..., min_length=1, max_length=500)
    description: str | None = None


class ImageUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    tag: str | None = Field(None, min_length=1, max_length=100)
    image_ref: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None


class ImageResponse(BaseModel):
    id: uuid.UUID
    name: str
    tag: str
    image_ref: str
    description: str | None = None
    source: str
    is_enabled: bool
    tenant_id: uuid.UUID | None = None
    build_status: BuildStatus | None = None
    dockerfile: str | None = None
    created_at: datetime
    updated_at: datetime


class ImageBuildRequest(BaseModel):
    dockerfile: str = Field(..., min_length=1, description="Dockerfile 内容")
    name: str = Field(..., min_length=1, max_length=200, description="目标镜像名称")
    tag: str = Field(..., min_length=1, max_length=100, description="目标镜像标签")
    description: str | None = Field(None, description="镜像描述")


class ImageBuildLogResponse(BaseModel):
    build_status: BuildStatus | None = None
    log: str = ""


class ImageListQuery(BaseModel):
    keyword: str | None = None
    source: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
