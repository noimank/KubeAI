import { api } from './api'
import type { PageData } from '@/types/api'
import type { Experiment } from '@/types/experiment'

export async function getExperiments(params: {
  current: number
  pageSize: number
  trainingJobName?: string
  status?: string
}): Promise<PageData<Experiment>> {
  const res = await api.get('/experiments', {
    params: {
      page: params.current,
      page_size: params.pageSize,
      training_job_name: params.trainingJobName,
      status: params.status,
    },
  })
  return res.data.data!
}

export async function getExperiment(id: string): Promise<Experiment> {
  const res = await api.get(`/experiments/${id}`)
  return res.data.data!
}
