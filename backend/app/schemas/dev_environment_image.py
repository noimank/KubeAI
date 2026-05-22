import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import EnvironmentType


class DevEnvironmentImageCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    environment_type: str = Field(..., min_length=1, max_length=20)
    image_ref: str = Field(..., min_length=1, max_length=500)
    description: str | None = None
    icon: str | None = None
    default_cpu: str = Field(default="2")
    default_memory: str = Field(default="4Gi")
    default_gpu_count: int = Field(default=0, ge=0)

    @field_validator("environment_type")
    @classmethod
    def validate_environment_type(cls, v: str) -> str:
        valid = {e.value for e in EnvironmentType}
        if v not in valid:
            raise ValueError(f"环境类型必须是 {', '.join(sorted(valid))} 之一")
        return v


class DevEnvironmentImageUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    environment_type: str | None = Field(None, min_length=1, max_length=20)
    image_ref: str | None = Field(None, min_length=1, max_length=500)
    description: str | None = None
    icon: str | None = None
    default_cpu: str | None = None
    default_memory: str | None = None
    default_gpu_count: int | None = Field(None, ge=0)

    @field_validator("environment_type")
    @classmethod
    def validate_environment_type(cls, v: str | None) -> str | None:
        if v is not None:
            valid = {e.value for e in EnvironmentType}
            if v not in valid:
                raise ValueError(f"环境类型必须是 {', '.join(sorted(valid))} 之一")
        return v


class DevEnvironmentImageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    environment_type: str
    image_ref: str
    description: str | None = None
    icon: str | None = None
    default_cpu: str
    default_memory: str
    default_gpu_count: int
    is_enabled: bool
    tenant_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class DevEnvironmentImageSelectableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    environment_type: str
    image_ref: str
    icon: str | None = None
    default_cpu: str
    default_memory: str
    default_gpu_count: int


class DevEnvironmentImageListQuery(BaseModel):
    keyword: str | None = None
    environment_type: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
