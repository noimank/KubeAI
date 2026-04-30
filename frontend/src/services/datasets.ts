import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type { Dataset } from '@/types/dataset'

export async function getDatasets(params: {
  current: number
  pageSize: number
  keyword?: string
  startDate?: string
  endDate?: string
}): Promise<PageData<Dataset>> {
  const { current, pageSize, ...rest } = params
  const res = await api.get<BaseResponse<PageData<Dataset>>>('/datasets', {
    params: { page: current, pageSize, ...rest },
  })
  return res.data.data!
}

export async function getDatasetDetail(id: string): Promise<BaseResponse<Dataset>> {
  const res = await api.get<BaseResponse<Dataset>>(`/datasets/${id}`)
  return res.data
}

export async function deleteDataset(id: string): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(`/datasets/${id}`)
  return res.data
}
