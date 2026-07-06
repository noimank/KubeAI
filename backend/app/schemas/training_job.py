import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class HyperparameterItem(BaseModel):
    key: str
    value: str


class TrainingJobCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    dataset_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    image_id: uuid.UUID
    command: str = Field(..., min_length=1)
    hyperparameters: list[HyperparameterItem] | None = None
    gpu_count: int = Field(default=1, ge=0)
    gpu_mode: str = Field(default="exclusive", pattern="^(exclusive|shared)$")
    cpu: str = Field(default="4")
    memory: str = Field(default="8Gi")
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    worker_count: int = Field(default=1, ge=1, le=16)
    source_experiment_id: uuid.UUID | None = None
    mlflow_enabled: bool = Field(default=False, description="是否启用 MLflow 实验追踪 (默认关闭)")
    tensorboard_enabled: bool = Field(default=False, description="是否启用 TensorBoard 可视化 (默认关闭)")


class TrainingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    description: str | None
    created_by: uuid.UUID
    dataset_id: uuid.UUID | None
    dataset_version_id: uuid.UUID | None
    image_id: uuid.UUID
    command: str
    hyperparameters: dict[str, str] | None
    gpu_count: int
    gpu_mode: str
    cpu: str
    memory: str
    priority: str
    worker_count: int
    status: str
    source: str
    source_env_id: uuid.UUID | None
    vcjob_name: str | None
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None
    workspace_path: str | None = None
    home_path: str | None = None
    mlflow_enabled: bool = False
    tensorboard_enabled: bool = False
    experiment_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class TrainingJobListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: str | None = None
    name: str | None = None


class PodInfoResponse(BaseModel):
    pod_name: str
    role: str
    status: str


class LogResponse(BaseModel):
    lines: list[str]
    has_more: bool
    total_lines: int


class TrainingJobFromEnvironmentRequest(BaseModel):
    environment_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    command: str = Field(min_length=1)
    description: str | None = None
    image_id: uuid.UUID | None = None
    dataset_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    gpu_count: int | None = Field(default=None, ge=0)
    gpu_mode: str = Field(default="exclusive", pattern="^(exclusive|shared)$")
    cpu: str | None = None
    memory: str | None = None
    priority: str = Field(default="normal", pattern="^(low|normal|high)$")
    worker_count: int = Field(default=1, ge=1, le=16)
    hyperparameters: list[HyperparameterItem] | None = None
    mlflow_enabled: bool = Field(default=False, description="是否启用 MLflow 实验追踪 (默认关闭)")
    tensorboard_enabled: bool = Field(default=False, description="是否启用 TensorBoard 可视化 (默认关闭)")
