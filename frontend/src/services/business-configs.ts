import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  BusinessConfig,
  BusinessConfigCreate,
  BusinessConfigUpdate,
} from '@/types/business-config'

export async function getBusinessConfigs(params: {
  current: number
  pageSize: number
  search?: string
}): Promise<PageData<BusinessConfig>> {
  const { current, pageSize, ...rest } = params
  const res = await api.get<BaseResponse<PageData<BusinessConfig>>>('/business-configs', {
    params: { page: current, pageSize, ...rest },
  })
  return res.data.data!
}

export async function getBusinessConfig(id: string): Promise<BusinessConfig> {
  const res = await api.get<BaseResponse<BusinessConfig>>(`/business-configs/${id}`)
  return res.data.data!
}

export async function createBusinessConfig(data: BusinessConfigCreate): Promise<BusinessConfig> {
  const res = await api.post<BaseResponse<BusinessConfig>>('/business-configs', data)
  return res.data.data!
}

export async function updateBusinessConfig(
  id: string,
  data: BusinessConfigUpdate,
): Promise<BusinessConfig> {
  const res = await api.put<BaseResponse<BusinessConfig>>(`/business-configs/${id}`, data)
  return res.data.data!
}

export async function deleteBusinessConfig(id: string): Promise<void> {
  await api.delete<BaseResponse<null>>(`/business-configs/${id}`)
}
