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

export interface QuotaAllocationItem {
  total: number
  allocated: number
  available: number
}

export interface QuotaAllocationOverview {
  gpu: QuotaAllocationItem
  cpu: QuotaAllocationItem
  memory: QuotaAllocationItem
  storage: QuotaAllocationItem
}

export interface TenantQuotaComparisonItem {
  quota: number
  used: number
  utilization: number
}

export interface TenantQuotaComparison {
  tenantId: string
  tenantName: string
  gpu: TenantQuotaComparisonItem
  cpu: TenantQuotaComparisonItem
  memory: TenantQuotaComparisonItem
  storage: TenantQuotaComparisonItem
}

export interface QuotaTransferRequest {
  sourceTenantId: string
  targetTenantId: string
  resourceType: 'gpu' | 'cpu' | 'memory' | 'storage'
  amount: string
  force?: boolean
}

export interface StaleJob {
  id: string
  name: string
  tenantName: string
  namespace: string
  vcjobName: string
  status: string
  finishedAt: string | null
  daysAgo: number
}

export interface OrphanPVC {
  name: string
  namespace: string
  storage: string
  createdAt: string | null
  orphanReason: string
}

export interface CleanupDetail {
  namespace: string
  pvcName: string
  success: boolean
  error?: string | null
}

export interface CleanupResult {
  cleanedCount: number
  failedCount: number
  details: CleanupDetail[]
}
