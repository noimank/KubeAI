from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ResourceMetric(BaseModel):
    total: int | float = 0
    used: int | float = 0
    utilization: float = 0.0


class ClusterOverviewResponse(BaseModel):
    gpu: ResourceMetric
    cpu: ResourceMetric
    memory: ResourceMetric
    storage: dict[str, Any]


class NodeResourceInfo(BaseModel):
    allocatable: int | float = 0
    allocated: int | float = 0


class NodeCondition(BaseModel):
    type: str
    status: str


class NodeResourceDetail(BaseModel):
    name: str
    gpu: NodeResourceInfo
    cpu: NodeResourceInfo
    memory: NodeResourceInfo
    conditions: list[NodeCondition] = []


class TenantQuotaUsed(BaseModel):
    used: int | float | str = 0
    quota: int | float | str = 0


class TenantResourceSummary(BaseModel):
    tenant_id: str
    tenant_name: str
    namespace: str | None = None
    gpu: TenantQuotaUsed
    cpu: TenantQuotaUsed
    memory: TenantQuotaUsed
    storage: TenantQuotaUsed
    active_jobs_count: int = 0
    running_services_count: int = 0


class JobSummary(BaseModel):
    id: str
    name: str
    status: str
    gpu_count: int


class ServiceSummary(BaseModel):
    id: str
    name: str
    status: str
    gpu_count: int


class TenantResourceDetail(BaseModel):
    tenant_id: str
    tenant_name: str
    namespace: str | None = None
    gpu: TenantQuotaUsed
    cpu: TenantQuotaUsed
    memory: TenantQuotaUsed
    storage: TenantQuotaUsed
    active_jobs: list[JobSummary] = []
    running_services: list[ServiceSummary] = []
