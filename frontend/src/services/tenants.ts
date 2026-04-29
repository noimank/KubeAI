import { api } from './api'
import type { BaseResponse, PageResponse } from '@/types/api'
import type {
  Tenant,
  TenantCreateRequest,
  TenantQuotaUpdateRequest,
  TenantUpdateRequest,
  QuotaUsage,
} from '@/types/tenant'

export async function getTenants(
  page: number = 1,
  pageSize: number = 20,
): Promise<PageResponse<Tenant>> {
  const res = await api.get<PageResponse<Tenant>>('/tenants', {
    params: { page, pageSize },
  })
  return res.data
}

export async function createTenant(data: TenantCreateRequest): Promise<BaseResponse<Tenant>> {
  const res = await api.post<BaseResponse<Tenant>>('/tenants', data)
  return res.data
}

export async function getTenant(id: string): Promise<BaseResponse<Tenant>> {
  const res = await api.get<BaseResponse<Tenant>>(`/tenants/${id}`)
  return res.data
}

export async function updateTenant(
  id: string,
  data: TenantUpdateRequest,
): Promise<BaseResponse<Tenant>> {
  const res = await api.put<BaseResponse<Tenant>>(`/tenants/${id}`, data)
  return res.data
}

export async function toggleTenantStatus(
  id: string,
  status: 'active' | 'disabled',
): Promise<BaseResponse<Tenant>> {
  const res = await api.patch<BaseResponse<Tenant>>(`/tenants/${id}/status`, { status })
  return res.data
}

export async function deleteTenant(id: string): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(`/tenants/${id}`)
  return res.data
}

export async function updateTenantQuota(
  id: string,
  data: TenantQuotaUpdateRequest,
): Promise<BaseResponse<Tenant>> {
  const res = await api.put<BaseResponse<Tenant>>(`/tenants/${id}/quota`, data)
  return res.data
}

export async function getTenantQuotaUsage(id: string): Promise<BaseResponse<QuotaUsage>> {
  const res = await api.get<BaseResponse<QuotaUsage>>(`/tenants/${id}/quota-usage`)
  return res.data
}
