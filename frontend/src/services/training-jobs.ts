import { api } from './api'
import type { PageData } from '@/types/api'
import type {
  LogData,
  PodInfo,
  TrainingJob,
  TrainingJobCreate,
  TrainingMetrics,
} from '@/types/training-job'
import { ACCESS_TOKEN_KEY, API_BASE_URL } from '@/utils/constants'

export async function getTrainingJobs(params: {
  current: number
  pageSize: number
  status?: string
  name?: string
}): Promise<PageData<TrainingJob>> {
  const res = await api.get('/training-jobs', {
    params: {
      page: params.current,
      page_size: params.pageSize,
      status: params.status,
      name: params.name,
    },
  })
  return res.data.data!
}

export async function getTrainingJob(id: string): Promise<TrainingJob> {
  const res = await api.get(`/training-jobs/${id}`)
  return res.data.data!
}

export async function createTrainingJob(data: TrainingJobCreate): Promise<TrainingJob> {
  const res = await api.post('/training-jobs', data)
  return res.data.data!
}

export async function stopTrainingJob(id: string): Promise<TrainingJob> {
  const res = await api.post(`/training-jobs/${id}/stop`)
  return res.data.data!
}

export async function retryTrainingJob(id: string): Promise<TrainingJob> {
  const res = await api.post(`/training-jobs/${id}/retry`)
  return res.data.data!
}

export async function getTrainingJobPods(id: string): Promise<PodInfo[]> {
  const res = await api.get(`/training-jobs/${id}/pods`)
  return res.data.data!
}

export async function getTrainingJobLogs(
  id: string,
  params?: { podName?: string; tailLines?: number },
): Promise<LogData> {
  const res = await api.get(`/training-jobs/${id}/logs`, { params })
  return res.data.data!
}

export function buildLogStreamUrl(
  jobId: string,
  params?: { podName?: string; tailLines?: number },
): string {
  const baseURL = API_BASE_URL
  const token = localStorage.getItem(ACCESS_TOKEN_KEY)
  const url = new URL(`${baseURL}/training-jobs/${jobId}/logs/stream`, window.location.origin)
  url.searchParams.set('token', token || '')
  if (params?.podName) url.searchParams.set('pod_name', params.podName)
  if (params?.tailLines) url.searchParams.set('tail_lines', String(params.tailLines))
  return url.toString()
}

export async function getTrainingJobMetrics(
  id: string,
  params?: { duration?: string; step?: string },
): Promise<TrainingMetrics> {
  const res = await api.get(`/training-jobs/${id}/metrics`, { params })
  return res.data.data!
}
