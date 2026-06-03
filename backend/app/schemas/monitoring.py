import uuid
from typing import Any, Literal

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


class QuotaAllocationItem(BaseModel):
    total: int | float = 0
    allocated: int | float = 0
    available: int | float = 0


class QuotaAllocationOverview(BaseModel):
    gpu: QuotaAllocationItem
    cpu: QuotaAllocationItem
    memory: QuotaAllocationItem


class TenantQuotaComparisonItem(BaseModel):
    quota: int | float = 0
    used: int | float = 0
    utilization: float = 0.0


class TenantQuotaComparison(BaseModel):
    tenant_id: str
    tenant_name: str
    gpu: TenantQuotaComparisonItem
    cpu: TenantQuotaComparisonItem
    memory: TenantQuotaComparisonItem
    storage: TenantQuotaComparisonItem


class QuotaTransferRequest(BaseModel):
    source_tenant_id: uuid.UUID
    target_tenant_id: uuid.UUID
    resource_type: Literal["gpu", "cpu", "memory", "storage"]
    amount: str
    force: bool = False


class StaleJobInfo(BaseModel):
    id: str
    name: str
    tenant_name: str
    namespace: str
    vcjob_name: str
    status: str
    finished_at: str | None = None
    days_ago: int
