import uuid
from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    email: str
    role: str = "algorithm_engineer"
    is_active: bool = True
    tenant_id: uuid.UUID | None = None
    created_at: datetime
