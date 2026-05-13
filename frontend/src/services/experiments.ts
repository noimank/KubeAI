import { api } from './api'
import type { PageData } from '@/types/api'
import type {
  Experiment,
  ExperimentComparison,
  ExperimentDetail,
  MetricHistoryPoint,
} from '@/types/experiment'

export async function getExperiments(params: {
  current: number
  pageSize: number
  trainingJobName?: string
  status?: string
  sortBy?: string
  sortOrder?: string
  datasetId?: string
  imageId?: string
  startDate?: string
  endDate?: string
}): Promise<PageData<Experiment>> {
  const res = await api.get('/experiments', {
    params: {
      page: params.current,
      page_size: params.pageSize,
      training_job_name: params.trainingJobName,
      status: params.status,
      sort_by: params.sortBy,
      sort_order: params.sortOrder,
      dataset_id: params.datasetId,
      image_id: params.imageId,
      start_date: params.startDate,
      end_date: params.endDate,
    },
  })
  return res.data.data!
}

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

export async function getMetricHistory(
  experimentId: string,
  metricKey: string,
): Promise<MetricHistoryPoint[]> {
  const res = await api.get(`/experiments/${experimentId}/metrics/${metricKey}/history`)
  return res.data.data!
}
