import { api } from './api'
import type { PageData } from '@/types/api'
import type { TrainingJob, TrainingJobCreate } from '@/types/training-job'

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
