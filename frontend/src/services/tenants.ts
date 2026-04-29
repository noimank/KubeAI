import { api } from './api'
import type { BaseResponse, PageResponse } from '@/types/api'
import type { Tenant, TenantCreateRequest } from '@/types/tenant'

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
