import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ModelDeployConfig(BaseModel):
    """模型版本推理部署参数 — 上传/注册时可选填写, 部署为推理服务时作为缺省值预填."""

    image_ids: list[uuid.UUID] = Field(default_factory=list, description="候选推理镜像, 有序, 首个为默认")
    container_port: int | None = Field(default=None, ge=1, le=65535)
    subpath_mode: Literal["rewrite", "native"] | None = None
    command: list[str] | None = None
    args: list[str] | None = None
    env_vars: dict[str, str] | None = None
    gpu_count: int | None = Field(default=None, ge=0)
    cpu: str | None = None
    memory: str | None = None
    replicas: int | None = Field(default=None, ge=1, le=10)


class DeployImageOption(BaseModel):
    image_id: uuid.UUID
    image_name: str | None = None
    image_tag: str | None = None


class ModelDeployConfigResponse(BaseModel):
    images: list[DeployImageOption] = Field(default_factory=list)
    container_port: int | None = Field(default=None, ge=1, le=65535)
    subpath_mode: Literal["rewrite", "native"] | None = None
    command: list[str] | None = None
    args: list[str] | None = None
    env_vars: dict[str, str] | None = None
    gpu_count: int | None = Field(default=None, ge=0)
    cpu: str | None = None
    memory: str | None = None
    replicas: int | None = Field(default=None, ge=1, le=10)


class ModelVersionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    file_paths: list[str] = Field(..., min_length=1)
    training_job_id: uuid.UUID | None = None
    deploy_config: ModelDeployConfig | None = None


class ModelVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    registered_model_id: uuid.UUID
    version_number: int
    description: str | None = None
    storage_path: str
    status: str = "uploading"
    file_count: int
    total_size_bytes: int
    training_job_id: uuid.UUID | None = None
    training_job_name: str | None = None
    dataset_id: uuid.UUID | None = None
    dataset_name: str | None = None
    dataset_version_id: uuid.UUID | None = None
    dataset_version_number: int | None = None
    image_id: uuid.UUID | None = None
    image_name: str | None = None
    image_tag: str | None = None
    hyperparameters: dict[str, str] | None = None
    deploy_config: ModelDeployConfigResponse | None = None
    created_by: uuid.UUID
    created_at: datetime


class ModelVersionFileResponse(BaseModel):
    file_name: str
    size_bytes: int = 0
    content_type: str = "application/octet-stream"
    last_modified: datetime | None = None


class ModelFileDownloadRequest(BaseModel):
    file_name: str


class RegisteredModelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    created_by_name: str | None = None
    version_count: int = 0
    latest_version: ModelVersionResponse | None = None
    created_at: datetime
    updated_at: datetime


class RegisteredModelDetailResponse(RegisteredModelResponse):
    versions: list[ModelVersionResponse] = []
