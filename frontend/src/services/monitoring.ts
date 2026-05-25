import { api } from './api'
import type { BaseResponse } from '@/types/api'
import type {
  ClusterOverview,
  NodeResourceDetail,
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
