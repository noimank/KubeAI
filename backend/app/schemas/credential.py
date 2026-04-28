from datetime import datetime

from pydantic import BaseModel, Field


class CredentialCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., min_length=1, max_length=50)
    data: dict[str, str]


class CredentialResponse(BaseModel):
    name: str
    type: str
    created_at: datetime | None = None
