import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.enums import BuildStatus

_IMAGE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_IMAGE_TAG_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")


class ImageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    tag: str = Field(..., min_length=1, max_length=100)
    image_ref: str = Field(..., min_length=1, max_length=500)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not _IMAGE_NAME_RE.match(v):
            raise ValueError("镜像名称只能包含小写字母,数字,点,下划线和连字符, 且以字母或数字开头")
        return v

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        if not _IMAGE_TAG_RE.match(v):
            raise ValueError("镜像标签只能包含字母,数字,点,下划线和连字符, 且以字母或数字开头")
        return v


class ImageUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    tag: str | None = Field(None, min_length=1, max_length=100)
    image_ref: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None and not _IMAGE_NAME_RE.match(v):
            raise ValueError("镜像名称只能包含小写字母,数字,点,下划线和连字符, 且以字母或数字开头")
        return v

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str | None) -> str | None:
        if v is not None and not _IMAGE_TAG_RE.match(v):
            raise ValueError("镜像标签只能包含字母,数字,点,下划线和连字符, 且以字母或数字开头")
        return v


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


class ImageSelectableResponse(BaseModel):
    id: uuid.UUID
    name: str
    tag: str
    image_ref: str
    source: str


class ImageBuildRequest(BaseModel):
    dockerfile: str = Field(..., min_length=1, description="Dockerfile 内容")
    name: str = Field(..., min_length=1, max_length=200, description="目标镜像名称")
    tag: str = Field(..., min_length=1, max_length=100, description="目标镜像标签")
    description: str | None = Field(None, description="镜像描述")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        if not _IMAGE_NAME_RE.match(v):
            raise ValueError("镜像名称只能包含小写字母,数字,点,下划线和连字符, 且以字母或数字开头")
        return v

    @field_validator("tag")
    @classmethod
    def validate_tag(cls, v: str) -> str:
        if not _IMAGE_TAG_RE.match(v):
            raise ValueError("镜像标签只能包含字母,数字,点,下划线和连字符, 且以字母或数字开头")
        return v


class ImageBuildLogResponse(BaseModel):
    build_status: BuildStatus | None = None
    log: str = ""


class ImageListQuery(BaseModel):
    keyword: str | None = None
    source: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
