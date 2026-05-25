from datetime import datetime

from pydantic import BaseModel


class DashboardResourceOverview(BaseModel):
    gpu_used: int = 0
    gpu_total: int = 0
    active_jobs: int = 0
    active_datasets: int = 0


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


class TenantRankingItem(BaseModel):
    tenant_id: str
    tenant_name: str
    gpu_quota: int = 0
    gpu_used: int = 0
    gpu_utilization: float = 0.0
    cpu_utilization: float = 0.0
    active_jobs: int = 0


class RecentAlert(BaseModel):
    id: str
    type: str
    title: str
    priority: str
    created_at: datetime


class ClusterOverviewBrief(BaseModel):
    gpu_total: int = 0
    gpu_used: int = 0
    gpu_utilization: float = 0.0
    cpu_total: int | float = 0
    cpu_used: int | float = 0
    cpu_utilization: float = 0.0
    memory_total: int | float = 0
    memory_used: int | float = 0
    memory_utilization: float = 0.0


class PendingAnnotationTask(BaseModel):
    id: str
    project_id: str
    project_name: str
    status: str
    total_tasks: int = 0
    completed_tasks: int = 0


class AnnotationProgressOverview(BaseModel):
    pending_count: int = 0
    today_completed: int = 0
    total_completion_rate: float = 0.0


class RecentInferenceService(BaseModel):
    id: str
    name: str
    status: str
    replicas: int = 1
    endpoint_url: str | None = None


class EngineerDashboard(BaseModel):
    resource_overview: DashboardResourceOverview
    recent_training_jobs: list[RecentTrainingJob]
    recent_datasets: list[RecentDataset]


class AdminDashboard(BaseModel):
    cluster_overview: ClusterOverviewBrief
    tenant_ranking: list[TenantRankingItem]
    recent_alerts: list[RecentAlert]


class AnnotatorDashboard(BaseModel):
    progress_overview: AnnotationProgressOverview
    pending_tasks: list[PendingAnnotationTask]


class MLOpsDashboard(BaseModel):
    resource_overview: DashboardResourceOverview
    recent_inference_services: list[RecentInferenceService]


class DashboardResponse(BaseModel):
    role: str
    data: EngineerDashboard | AdminDashboard | AnnotatorDashboard | MLOpsDashboard
