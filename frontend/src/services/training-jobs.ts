import { api } from './api'
import type { PageData } from '@/types/api'
import type {
  LogData,
  PodInfo,
  TrainingJob,
  TrainingJobCreate,
  TrainingMetrics,
} from '@/types/training-job'
import { API_BASE_URL } from '@/utils/constants'

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

export async function deleteTrainingJob(id: string): Promise<void> {
  await api.delete(`/training-jobs/${id}`)
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

export function buildLogStreamWsUrl(
  jobId: string,
  params?: { podName?: string; tailLines?: number },
): string {
  // WebSocket 日志流; token 由 LogStream 在连接时通过 appendAuthToken 附加(刷新后重连用最新值)。
  const url = new URL(`${API_BASE_URL}/training-jobs/${jobId}/logs/ws`, window.location.origin)
  url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
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
