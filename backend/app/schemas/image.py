import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
    created_at: datetime
    updated_at: datetime


class ImageListQuery(BaseModel):
    keyword: str | None = None
    source: str | None = None
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
