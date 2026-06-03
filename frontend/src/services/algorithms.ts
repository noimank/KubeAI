import { api } from './api'
import type { BaseResponse, PageData } from '@/types/api'
import type { Algorithm, AlgorithmDetail, AlgorithmUpdateParams } from '@/types/algorithm'

export async function getAlgorithms(params: {
  current: number
  pageSize: number
  name?: string
  tag?: string
  uploader?: string
}): Promise<PageData<Algorithm>> {
  const { current, pageSize, ...rest } = params
  const res = await api.get<BaseResponse<PageData<Algorithm>>>('/algorithms', {
    params: { page: current, pageSize, ...rest },
  })
  return res.data.data!
}

export async function getAlgorithm(id: string): Promise<AlgorithmDetail> {
  const res = await api.get<BaseResponse<AlgorithmDetail>>(`/algorithms/${id}`)
  return res.data.data!
}

export async function createAlgorithm(params: {
  name: string
  description?: string
  tags?: string
  file: File
}): Promise<AlgorithmDetail> {
  const formData = new FormData()
  formData.append('name', params.name)
  if (params.description) formData.append('description', params.description)
  if (params.tags) formData.append('tags', params.tags)
  formData.append('file', params.file)

  const res = await api.post<BaseResponse<AlgorithmDetail>>('/algorithms', formData, {
    params: {
      name: params.name,
      description: params.description || undefined,
      tags: params.tags || undefined,
    },
  })
  return res.data.data!
}

export async function updateAlgorithm(
  id: string,
  params: AlgorithmUpdateParams,
): Promise<Algorithm> {
  const res = await api.patch<BaseResponse<Algorithm>>(`/algorithms/${id}`, params)
  return res.data.data!
}

export async function deleteAlgorithm(id: string): Promise<void> {
  await api.delete(`/algorithms/${id}`)
}

export async function downloadAlgorithm(id: string, filename?: string): Promise<void> {
  const res = await api.get(`/algorithms/${id}/download`, {
    responseType: 'blob',
    // @ts-expect-error _skipErrorHandler is a custom Axios config extension
    _skipErrorHandler: true,
  })

  const blob = res.data as Blob
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'algorithm.zip'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
