import { api } from './api'
import type { PageData } from '@/types/api'
import type { InferenceService, InferenceServiceCreate } from '@/types/inference'

export async function getInferenceServices(params: {
  current: number
  pageSize: number
  status?: string
  name?: string
}): Promise<PageData<InferenceService>> {
  const res = await api.get('/inference-services', {
    params: {
      page: params.current,
      page_size: params.pageSize,
      status: params.status,
      name: params.name,
    },
  })
  return res.data.data!
}

export async function getInferenceService(id: string): Promise<InferenceService> {
  const res = await api.get(`/inference-services/${id}`)
  return res.data.data!
}

export async function createInferenceService(
  data: InferenceServiceCreate,
): Promise<InferenceService> {
  const res = await api.post('/inference-services', data)
  return res.data.data!
}

export async function stopInferenceService(id: string): Promise<InferenceService> {
  const res = await api.post(`/inference-services/${id}/stop`)
  return res.data.data!
}

export async function deleteInferenceService(id: string): Promise<InferenceService> {
  const res = await api.delete(`/inference-services/${id}`)
  return res.data.data!
}
