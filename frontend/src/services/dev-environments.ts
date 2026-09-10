import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type {
  DevEnvironment,
  DevEnvironmentCreateParams,
  AccessUrlResponse,
} from '@/types/dev-environment'

export async function getDevEnvironments(params: {
  current: number
  pageSize: number
  status?: string
  name?: string
}): Promise<PageData<DevEnvironment>> {
  const res = await api.get<BaseResponse<PageData<DevEnvironment>>>('/dev-environments', {
    params: {
      page: params.current,
      page_size: params.pageSize,
      status: params.status,
      name: params.name,
    },
  })
  return res.data.data!
}

export async function getDevEnvironment(id: string): Promise<DevEnvironment> {
  const res = await api.get<BaseResponse<DevEnvironment>>(`/dev-environments/${id}`)
  return res.data.data!
}

export async function createDevEnvironment(
  data: DevEnvironmentCreateParams,
): Promise<DevEnvironment> {
  const res = await api.post<BaseResponse<DevEnvironment>>('/dev-environments', data)
  return res.data.data!
}

export async function stopDevEnvironment(id: string): Promise<DevEnvironment> {
  const res = await api.post<BaseResponse<DevEnvironment>>(`/dev-environments/${id}/stop`)
  return res.data.data!
}

export async function startDevEnvironment(id: string): Promise<DevEnvironment> {
  const res = await api.post<BaseResponse<DevEnvironment>>(`/dev-environments/${id}/start`)
  return res.data.data!
}

export async function deleteDevEnvironment(id: string): Promise<DevEnvironment> {
  const res = await api.delete<BaseResponse<DevEnvironment>>(`/dev-environments/${id}`)
  return res.data.data!
}

export async function getAccessUrl(id: string): Promise<AccessUrlResponse> {
  const res = await api.get<BaseResponse<AccessUrlResponse>>(`/dev-environments/${id}/access-url`)
  return res.data.data!
}
