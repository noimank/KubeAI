import { api } from './api'
import type { PageData } from '@/types/api'
import type {
  ModelDeployConfigInput,
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

export async function uploadModelFiles(params: {
  name?: string
  modelId?: string
  description?: string
  trainingJobId?: string
  deployConfig?: ModelDeployConfigInput
  files: File[]
}): Promise<ModelVersion> {
  const formData = new FormData()
  if (params.name) formData.append('name', params.name)
  if (params.modelId) formData.append('model_id', params.modelId)
  if (params.description) formData.append('description', params.description)
  if (params.trainingJobId) formData.append('training_job_id', params.trainingJobId)
  if (params.deployConfig) {
    // multipart 不走 axios 的 camelCase→snake_case JSON 转换, 手动按后端字段名序列化
    const c = params.deployConfig
    formData.append(
      'deploy_config',
      JSON.stringify({
        image_ids: c.imageIds ?? [],
        container_port: c.containerPort ?? null,
        subpath_mode: c.subpathMode ?? null,
        command: c.command ?? null,
        args: c.args ?? null,
        env_vars: c.envVars ?? null,
        gpu_count: c.gpuCount ?? null,
        cpu: c.cpu ?? null,
        memory: c.memory ?? null,
        replicas: c.replicas ?? null,
      }),
    )
  }
  params.files.forEach((f) => formData.append('files', f))
  const res = await api.post('/model-registry/local-upload', formData)
  return res.data.data!
}

export async function updateModelVersionDeployConfig(
  modelId: string,
  versionId: string,
  data: ModelDeployConfigInput,
): Promise<ModelVersion> {
  const res = await api.patch(
    `/model-registry/${modelId}/versions/${versionId}/deploy-config`,
    data,
  )
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

export async function deleteModelVersion(modelId: string, versionId: string): Promise<void> {
  await api.delete(`/model-registry/${modelId}/versions/${versionId}`)
}

export async function deleteModel(modelId: string): Promise<void> {
  await api.delete(`/model-registry/${modelId}`)
}
