import { api } from './api'
import type { PageData } from '@/types/api'
import type {
  AutoScalingUpdateRequest,
  InferenceService,
  InferenceServiceCreate,
  InferenceServiceEvent,
  InferenceServiceScaleRequest,
} from '@/types/inference'

export interface InferenceServiceCreateResult extends InferenceService {
  authToken: string
}

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
): Promise<InferenceServiceCreateResult> {
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

export async function regenerateToken(id: string): Promise<string> {
  const res = await api.post(`/inference-services/${id}/regenerate-token`)
  return res.data.data!.token
}

export async function getInferenceServiceEvents(id: string): Promise<InferenceServiceEvent[]> {
  const res = await api.get(`/inference-services/${id}/events`)
  return res.data.data!
}

export async function scaleInferenceService(
  id: string,
  data: InferenceServiceScaleRequest,
): Promise<InferenceService> {
  const res = await api.post(`/inference-services/${id}/scale`, data)
  return res.data.data!
}

export async function updateAutoScaling(
  id: string,
  data: AutoScalingUpdateRequest,
): Promise<InferenceService> {
  const res = await api.patch(`/inference-services/${id}/autoscaling`, data)
  return res.data.data!
}
