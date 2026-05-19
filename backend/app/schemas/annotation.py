import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.enums import AnnotationType


class AnnotationProjectCreateRequest(BaseModel):
    name: str = Field(max_length=200)
    description: str | None = None
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    annotation_type: AnnotationType


class AnnotationProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    dataset_id: uuid.UUID
    dataset_version_id: uuid.UUID
    annotation_type: str
    label_studio_project_id: int | None
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
    label_config: str
    labeling_template_description: str | None = None


class AnnotationTemplateResponse(BaseModel):
    key: str
    label: str
    description: str


class AnnotationTaskResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    label_studio_task_id: int
    data: dict[str, Any]
    assigned_to: uuid.UUID | None = None
    assigned_to_name: str | None = None
    status: str
    project_name: str | None = None
    annotation_type: str | None = None
    created_at: datetime
    updated_at: datetime


class AnnotationTaskAssignRequest(BaseModel):
    task_ids: list[uuid.UUID] = Field(min_length=1)
    user_id: uuid.UUID


class AnnotationBatchAssignRequest(BaseModel):
    user_ids: list[uuid.UUID] = Field(min_length=1)
    tasks_per_user: int = Field(ge=1)


class AnnotationTaskSummaryResponse(BaseModel):
    project_id: uuid.UUID
    project_name: str
    annotation_type: str
    total_tasks: int
    assigned_tasks: int
    completed_tasks: int
