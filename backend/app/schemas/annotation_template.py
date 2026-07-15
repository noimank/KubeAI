import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AnnotationTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    label_config: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    group: str = Field(default="其他", min_length=1, max_length=100)


class AnnotationTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    label_config: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    group: str | None = Field(default=None, min_length=1, max_length=100)


class AnnotationTemplateResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    tags: list[str]
    group: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime


class AnnotationTemplateDetailResponse(AnnotationTemplateResponse):
    label_config: str
    project_count: int = 0


class AnnotationTemplateImportItem(BaseModel):
    """Label Studio /api/templates 模板条目."""

    key: str
    label: str
    description: str
    config: str
    group: str
