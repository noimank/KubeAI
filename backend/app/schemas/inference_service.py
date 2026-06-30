import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AutoScalingConfig(BaseModel):
    scaling_mode: Literal["fixed", "auto"] = "fixed"
    min_replicas: int = Field(default=0, ge=0, le=100)
    max_replicas: int = Field(default=1, ge=1, le=100)
    target_metric_type: Literal["gpu", "cpu"] | None = None
    target_metric_value: int | None = Field(default=None, ge=1)
    cooldown_period: int = Field(default=300, ge=0, le=3600)
    polling_interval: int = Field(default=30, ge=5, le=300)

    @model_validator(mode="after")
    def _validate_auto_mode(self) -> "AutoScalingConfig":
        if self.scaling_mode == "auto":
            if self.target_metric_type is None:
                raise ValueError("自动伸缩模式下必须指定指标类型")
            if self.target_metric_value is None:
                raise ValueError("自动伸缩模式下必须指定指标阈值")
            if self.min_replicas >= self.max_replicas:
                raise ValueError("最小副本数必须小于最大副本数")
        return self


class InferenceServiceCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    gpu_count: int = Field(default=0, ge=0)
    cpu: str = Field(default="2")
    memory: str = Field(default="4Gi")
    replicas: int = Field(default=1, ge=1)
    image: str | None = None
    image_id: uuid.UUID | None = None
    model_version_id: uuid.UUID | None = None
    container_port: int | None = Field(default=None, ge=1, le=65535)
    command: list[str] | None = None
    args: list[str] | None = None
    env_vars: dict[str, str] | None = None
    description: str | None = None
    auto_scaling: AutoScalingConfig | None = None

    @model_validator(mode="after")
    def _validate_required(self) -> "InferenceServiceCreateRequest":
        if self.image_id is None and not self.image:
            raise ValueError("必须选择推理运行时镜像")
        if self.container_port is None:
            raise ValueError("必须指定容器端口")
        return self


class ModelVersionSummary(BaseModel):
    id: uuid.UUID
    version_number: int
    registered_model_id: uuid.UUID
    model_name: str = ""
    status: str


class InferenceServiceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by: uuid.UUID
    name: str
    model_version_id: uuid.UUID | None = None
    image: str | None
    container_port: int | None = None
    command: str | None = None
    args: str | None = None
    gpu_count: int
    cpu: str
    memory: str
    replicas: int
    min_replicas: int
    max_replicas: int
    status: str
    endpoint_url: str | None
    proxy_endpoint: str | None
    has_token: bool = False
    description: str | None
    env_vars: dict[str, str] | None
    error_message: str | None = None
    scaling_mode: str = "fixed"
    target_metric_type: str | None = None
    target_metric_value: int | None = None
    cooldown_period: int = 300
    polling_interval: int = 30
    created_at: datetime
    updated_at: datetime
    model_version: ModelVersionSummary | None = None


class InferenceServiceListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    status: str | None = None
    name: str | None = None


class TokenRegenerateResponse(BaseModel):
    token: str
    message: str


class InferenceServiceCreateResponse(InferenceServiceResponse):
    auth_token: str


class InferenceServiceScaleRequest(BaseModel):
    replicas: int = Field(..., ge=0, le=100, description="目标副本数")


class InferenceServiceScaleResponse(InferenceServiceResponse):
    pass


class AutoScalingUpdateRequest(BaseModel):
    scaling_mode: Literal["fixed", "auto"] = "auto"
    min_replicas: int = Field(default=0, ge=0, le=100)
    max_replicas: int = Field(default=1, ge=1, le=100)
    target_metric_type: Literal["gpu", "cpu"] | None = None
    target_metric_value: int | None = Field(default=None, ge=1)
    cooldown_period: int = Field(default=300, ge=0, le=3600)
    polling_interval: int = Field(default=30, ge=5, le=300)

    @model_validator(mode="after")
    def _validate_auto_mode(self) -> "AutoScalingUpdateRequest":
        if self.scaling_mode == "auto":
            if self.target_metric_type is None:
                raise ValueError("自动伸缩模式下必须指定指标类型")
            if self.target_metric_value is None:
                raise ValueError("自动伸缩模式下必须指定指标阈值")
            if self.min_replicas >= self.max_replicas:
                raise ValueError("最小副本数必须小于最大副本数")
        return self


class InferenceServiceEventResponse(BaseModel):
    type: str
    reason: str
    message: str
    involved_object_kind: str
    involved_object_name: str
    count: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None


class GpuMetricPoint(BaseModel):
    """单张 GPU 的瞬时指标快照."""

    gpu_index: int
    utilization_percent: float
    memory_used_mib: float
    memory_total_mib: float
    temperature_c: float
    power_w: float


class TimeSeriesPoint(BaseModel):
    """时序数据点."""

    timestamp: str
    value: float
    label: str


class InferenceServiceMetricsResponse(BaseModel):
    """推理服务 GPU 监控指标响应."""

    gpu_metrics: list[GpuMetricPoint]
    gpu_utilization_history: list[TimeSeriesPoint]
    metrics_url: str | None
    prometheus_available: bool
    timestamp: str
