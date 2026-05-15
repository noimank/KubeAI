export type InferenceServiceStatus = 'pending' | 'deploying' | 'running' | 'failed' | 'stopped'

export interface ModelVersionSummary {
  id: string
  versionNumber: number
  registeredModelId: string
  status: string
}

export interface InferenceService {
  id: string
  tenantId: string
  createdBy: string
  name: string
  modelVersionId: string
  image?: string
  gpuCount: number
  cpu: string
  memory: string
  replicas: number
  minReplicas: number
  maxReplicas: number
  status: InferenceServiceStatus
  kserveName?: string
  endpointUrl?: string
  proxyEndpoint?: string
  hasToken: boolean
  description?: string
  envVars?: Record<string, string>
  createdAt: string
  updatedAt: string
  modelVersion?: ModelVersionSummary
}

export interface InferenceServiceCreate {
  name: string
  modelVersionId: string
  gpuCount?: number
  cpu?: string
  memory?: string
  replicas?: number
  image?: string
  envVars?: Record<string, string>
  description?: string
}
