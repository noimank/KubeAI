import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AnnotationProjectCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str | None = None
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    template_id: uuid.UUID


class AnnotationProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    template_id: uuid.UUID | None
    template_name: str | None = None
    total_tasks: int
    completed_tasks: int
    status: str
    created_by: uuid.UUID
    created_at: datetime
    updated_at: datetime
    tenant_id: uuid.UUID
    dataset_name: str | None = None
    dataset_version_number: int | None = None
    progress_percent: float = 0.0


class AnnotationProjectDetailResponse(AnnotationProjectResponse):
    label_config: str | None
    labeling_template_description: str | None = None


class SyncTasksResponse(BaseModel):
    synced_count: int


class MyTaskIdsResponse(BaseModel):
    """工作台线性导航的数据源:稳定排序的任务 ID 列表 + 当前用户已完成数。"""

    task_ids: list[uuid.UUID]
    completed_count: int


class AnnotationTaskResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    data: dict[str, Any]
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    status: str
    project_name: str | None = None
    template_name: str | None = None
    result: list[dict[str, Any]] | None = None
    submitted_at: datetime | None = None
    submitted_by: uuid.UUID | None = None
    annotation_payload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime


class AnnotationTaskAssignRequest(BaseModel):
    task_ids: list[uuid.UUID] = Field(min_length=1)
    user_id: uuid.UUID


class AnnotationBatchAssignRequest(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1)
    tasks_per_user: int = Field(ge=1)


class AnnotationTaskUnassignRequest(BaseModel):
    task_ids: list[uuid.UUID] = Field(min_length=1)


class AnnotationSubmitRequest(BaseModel):
    result: list[dict[str, Any]]


class AnnotationTaskSummaryResponse(BaseModel):
    project_id: uuid.UUID
    project_name: str
    template_name: str
    total_tasks: int
    assigned_tasks: int
    completed_tasks: int
