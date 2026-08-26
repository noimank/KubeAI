import { api } from './api'
import type { PageData } from '@/types/api'
import type {
  LogData,
  PodInfo,
  TrainingJob,
  TrainingJobCreate,
  TrainingMetrics,
} from '@/types/training-job'
import { buildWsUrl } from '@/utils/constants'

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
  // WebSocket 日志流; 同源 Cookie 鉴权, pod_name/tail_lines 为非敏感查询参数。
  const search = new URLSearchParams()
  if (params?.podName) search.set('pod_name', params.podName)
  if (params?.tailLines) search.set('tail_lines', String(params.tailLines))
  const query = search.toString()
  return buildWsUrl(`/training-jobs/${jobId}/logs/ws`) + (query ? `?${query}` : '')
}

export async function getTrainingJobMetrics(
  id: string,
  params?: { duration?: string; step?: string },
): Promise<TrainingMetrics> {
  const res = await api.get(`/training-jobs/${id}/metrics`, { params })
  return res.data.data!
}
