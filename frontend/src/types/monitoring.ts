export interface ResourceMetric {
  total: number
  used: number
  utilization: number
}

export interface ClusterOverview {
  gpu: ResourceMetric
  cpu: ResourceMetric
  memory: ResourceMetric
  storage: { used: number }
}

export interface NodeResourceInfo {
  allocatable: number
  allocated: number
}

export interface NodeCondition {
  type: string
  status: string
}

export interface NodeResourceDetail {
  name: string
  gpu: NodeResourceInfo
  cpu: NodeResourceInfo
  memory: NodeResourceInfo
  conditions: NodeCondition[]
}

export interface TenantQuotaUsed {
  used: number | string
  quota: number | string
}

export interface TenantResourceSummary {
  tenantId: string
  tenantName: string
  namespace?: string
  gpu: TenantQuotaUsed
  cpu: TenantQuotaUsed
  memory: TenantQuotaUsed
  storage: TenantQuotaUsed
  activeJobsCount: number
  runningServicesCount: number
}

export interface JobSummary {
  id: string
  name: string
  status: string
  gpuCount: number
}

export interface ServiceSummary {
  id: string
  name: string
  status: string
  gpuCount: number
}

export interface TenantResourceDetail {
  tenantId: string
  tenantName: string
  namespace?: string
  gpu: TenantQuotaUsed
  cpu: TenantQuotaUsed
  memory: TenantQuotaUsed
  storage: TenantQuotaUsed
  activeJobs: JobSummary[]
  runningServices: ServiceSummary[]
}
