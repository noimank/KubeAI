"""业务配置 Pydantic Schema。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BusinessConfigCreate(BaseModel):
    """创建业务配置请求。"""

    name: str = Field(..., min_length=1, max_length=100, description="配置名称")
    description: str | None = Field(None, max_length=500, description="描述")
    env_vars: dict[str, str] = Field(default_factory=dict, description="环境变量键值对")


class BusinessConfigUpdate(BaseModel):
    """更新业务配置请求，所有字段可选。"""

    name: str | None = Field(None, min_length=1, max_length=100, description="配置名称")
    description: str | None = Field(None, max_length=500, description="描述")
    env_vars: dict[str, str] | None = Field(None, description="环境变量键值对")


class BusinessConfigResponse(BaseModel):
    """业务配置响应。"""

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    name: str
    description: str | None = None
    env_vars: dict[str, str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
