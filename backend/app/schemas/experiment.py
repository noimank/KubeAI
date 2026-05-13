import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    training_job_id: uuid.UUID
    training_job_name: str | None = None
    mlflow_experiment_id: str | None
    mlflow_run_id: str | None
    status: str
    hyperparameters: dict[str, str] | None = None
    metrics: list[dict[str, object]] | None = None
    dataset_version: str | None = None
    image_name: str | None = None
    created_at: datetime
    updated_at: datetime


class MetricHistoryPoint(BaseModel):
    step: int
    value: float
    timestamp: float


class TrainingJobInfo(BaseModel):
    id: uuid.UUID
    name: str | None = None
    command: str | None = None
    dataset_version: str | None = None
    image_name: str | None = None
    gpu_count: int | None = None
    cpu: str | None = None
    memory: str | None = None
    dataset_id: uuid.UUID | None = None
    dataset_version_id: uuid.UUID | None = None
    image_id: uuid.UUID | None = None
    gpu_mode: str | None = None
    worker_count: int | None = None
    priority: str | None = None
    metrics_port: int | None = None


class ExperimentDetailResponse(ExperimentResponse):
    metric_histories: dict[str, list[MetricHistoryPoint]] | None = None
    duration_seconds: int | None = None
    training_job: TrainingJobInfo | None = None


class ExperimentListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    training_job_name: str | None = None
    status: str | None = None
    sort_by: str | None = None
    sort_order: str | None = Field(default=None, pattern=r"^(asc|desc)$")
    dataset_id: uuid.UUID | None = None
    image_id: uuid.UUID | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None


class HyperparamDiff(BaseModel):
    key: str
    values: dict[str, str | None]
    is_different: bool


class MetricComparison(BaseModel):
    metric_key: str
    series: dict[str, list[MetricHistoryPoint]]


class ExperimentComparisonResponse(BaseModel):
    experiments: list[ExperimentResponse]
    hyperparams_diff: list[HyperparamDiff]
    metrics_comparison: list[MetricComparison]


class CompareRequest(BaseModel):
    experiment_ids: list[uuid.UUID] = Field(..., min_length=2, max_length=5)
