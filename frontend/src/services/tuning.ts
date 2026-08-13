import { api } from './api'
import type { PageData } from '@/types/api'
import type {
  BestTrial,
  TuningInsights,
  TuningStudy,
  TuningStudyCreate,
  TuningTrial,
} from '@/types/tuning'

export async function getTuningStudies(params: {
  current: number
  pageSize: number
  status?: string
  name?: string
}): Promise<PageData<TuningStudy>> {
  const res = await api.get('/tuning/studies', {
    params: {
      page: params.current,
      page_size: params.pageSize,
      status: params.status,
      name: params.name,
    },
  })
  return res.data.data!
}

export async function getTuningStudy(id: string): Promise<TuningStudy> {
  const res = await api.get(`/tuning/studies/${id}`)
  return res.data.data!
}

export async function createTuningStudy(data: TuningStudyCreate): Promise<TuningStudy> {
  const res = await api.post('/tuning/studies', data)
  return res.data.data!
}

export async function getTuningTrials(id: string): Promise<TuningTrial[]> {
  const res = await api.get(`/tuning/studies/${id}/trials`)
  return res.data.data!
}

export async function getBestTrial(id: string): Promise<BestTrial> {
  const res = await api.get(`/tuning/studies/${id}/best`)
  return res.data.data!
}

export async function getTuningInsights(id: string): Promise<TuningInsights> {
  const res = await api.get(`/tuning/studies/${id}/insights`)
  return res.data.data!
}

export async function stopTuningStudy(id: string): Promise<TuningStudy> {
  const res = await api.post(`/tuning/studies/${id}/stop`)
  return res.data.data!
}

export async function pauseTuningStudy(id: string): Promise<TuningStudy> {
  const res = await api.post(`/tuning/studies/${id}/pause`)
  return res.data.data!
}

export async function resumeTuningStudy(id: string): Promise<TuningStudy> {
  const res = await api.post(`/tuning/studies/${id}/resume`)
  return res.data.data!
}

export async function deleteTuningStudy(id: string): Promise<void> {
  await api.delete(`/tuning/studies/${id}`)
}
