import { api } from './api'
import type { BaseResponse } from '@/types/api'
import type {
  CleanupResult,
  ClusterOverview,
  NodeResourceDetail,
  OrphanPVC,
  QuotaAllocationOverview,
  QuotaTransferRequest,
  StaleJob,
  TenantQuotaComparison,
  TenantResourceDetail,
  TenantResourceSummary,
} from '@/types/monitoring'

export async function getClusterOverview(): Promise<BaseResponse<ClusterOverview>> {
  const res = await api.get<BaseResponse<ClusterOverview>>('/monitoring/cluster-overview')
  return res.data
}

export async function getNodeDetails(): Promise<BaseResponse<NodeResourceDetail[]>> {
  const res = await api.get<BaseResponse<NodeResourceDetail[]>>('/monitoring/nodes')
  return res.data
}

export async function getTenantResourceSummary(): Promise<BaseResponse<TenantResourceSummary[]>> {
  const res = await api.get<BaseResponse<TenantResourceSummary[]>>('/monitoring/tenants')
  return res.data
}

export async function getTenantResourceDetail(
  tenantId: string,
): Promise<BaseResponse<TenantResourceDetail>> {
  const res = await api.get<BaseResponse<TenantResourceDetail>>(`/monitoring/tenants/${tenantId}`)
  return res.data
}

export async function getQuotaAllocationOverview(): Promise<BaseResponse<QuotaAllocationOverview>> {
  const res = await api.get<BaseResponse<QuotaAllocationOverview>>('/monitoring/quota-allocation')
  return res.data
}

export async function getQuotaComparison(): Promise<BaseResponse<TenantQuotaComparison[]>> {
  const res = await api.get<BaseResponse<TenantQuotaComparison[]>>('/monitoring/quota-comparison')
  return res.data
}

export async function transferQuota(data: QuotaTransferRequest): Promise<BaseResponse<null>> {
  const res = await api.post<BaseResponse<null>>('/monitoring/quota-transfer', data)
  return res.data
}

export async function getStaleJobs(): Promise<BaseResponse<StaleJob[]>> {
  const res = await api.get<BaseResponse<StaleJob[]>>('/monitoring/cleanup/stale-jobs')
  return res.data
}

export async function getOrphanPVCs(): Promise<BaseResponse<OrphanPVC[]>> {
  const res = await api.get<BaseResponse<OrphanPVC[]>>('/monitoring/cleanup/orphan-pvcs')
  return res.data
}

export async function cleanupPVCs(items: [string, string][]): Promise<BaseResponse<CleanupResult>> {
  const res = await api.post<BaseResponse<CleanupResult>>('/monitoring/cleanup/pvcs', { items })
  return res.data
}

export async function triggerCleanup(): Promise<BaseResponse<null>> {
  const res = await api.post<BaseResponse<null>>('/monitoring/cleanup/trigger')
  return res.data
}
