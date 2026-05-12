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


class ExperimentDetailResponse(ExperimentResponse):
    pass


class ExperimentListParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    training_job_name: str | None = None
    status: str | None = None
