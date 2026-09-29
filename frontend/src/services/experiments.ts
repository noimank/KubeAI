import { api } from './api'
import type { ExperimentComparison, ExperimentDetail } from '@/types/experiment'

export async function getExperiment(id: string): Promise<ExperimentDetail> {
  const res = await api.get(`/experiments/${id}`)
  return res.data.data!
}

export async function compareExperiments(ids: string[]): Promise<ExperimentComparison> {
  const res = await api.post('/experiments/compare', {
    experiment_ids: ids,
  })
  return res.data.data!
}
