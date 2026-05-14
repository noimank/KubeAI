import { api } from './api'
import type { PageData } from '@/types/api'
import type {
  ModelVersion,
  ModelVersionCreate,
  ModelVersionFile,
  RegisteredModel,
  RegisteredModelDetail,
} from '@/types/model'

export async function getModels(params: {
  current: number
  pageSize: number
  search?: string
}): Promise<PageData<RegisteredModel>> {
  const res = await api.get('/model-registry', {
    params: {
      page: params.current,
      page_size: params.pageSize,
      search: params.search || undefined,
    },
  })
  return res.data.data!
}

export async function getModel(id: string): Promise<RegisteredModelDetail> {
  const res = await api.get(`/model-registry/${id}`)
  return res.data.data!
}

export async function getModelVersion(modelId: string, versionId: string): Promise<ModelVersion> {
  const res = await api.get(`/model-registry/${modelId}/versions/${versionId}`)
  return res.data.data!
}

export async function registerModel(data: ModelVersionCreate): Promise<ModelVersion> {
  const res = await api.post('/model-registry', data)
  return res.data.data!
}

export async function getModelVersionFiles(
  modelId: string,
  versionId: string,
): Promise<ModelVersionFile[]> {
  const res = await api.get(`/model-registry/${modelId}/versions/${versionId}/files`)
  return res.data.data!
}

export async function getModelFileDownloadUrl(
  modelId: string,
  versionId: string,
  fileName: string,
): Promise<string> {
  const res = await api.post(
    `/model-registry/${modelId}/versions/${versionId}/files/download-url`,
    { fileName },
  )
  return res.data.data!
}
