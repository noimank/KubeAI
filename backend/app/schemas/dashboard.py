from datetime import datetime

from pydantic import BaseModel


class RecentTrainingJob(BaseModel):
    id: str
    name: str
    status: str
    gpu_count: int
    created_at: datetime


class RecentDataset(BaseModel):
    id: str
    name: str
    display_name: str | None = None
    version_count: int = 0
    file_count: int = 0
    updated_at: datetime | None = None


class RecentInferenceService(BaseModel):
    id: str
    name: str
    status: str
    replicas: int = 1
    endpoint_url: str | None = None


class PendingAnnotationProject(BaseModel):
    project_id: str
    project_name: str
    total_tasks: int = 0
    completed_tasks: int = 0


class DashboardResponse(BaseModel):
    """统一概览数据: 各明细分区按用户权限裁剪, 无权限的分区为 null."""

    recent_training_jobs: list[RecentTrainingJob] | None = None
    recent_datasets: list[RecentDataset] | None = None
    recent_inference_services: list[RecentInferenceService] | None = None
    pending_annotations: list[PendingAnnotationProject] | None = None
