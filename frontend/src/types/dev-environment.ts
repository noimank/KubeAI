export type DevEnvironmentStatus = 'pending' | 'creating' | 'running' | 'stopped' | 'failed'

export interface DatasetMountInfo {
  datasetId: string
  datasetName: string
  versionId?: string
  versionNumber?: string
  mountPath: string
}

export interface DevEnvironment {
  id: string
  tenantId: string
  createdBy: string
  name: string
  image: string
  gpuCount: number
  cpu: string
  memory: string
  status: DevEnvironmentStatus
  spawnerName?: string
  accessUrl?: string
  environmentImageId?: string
  environmentType?: string
  description?: string
  envVars?: Record<string, string>
  errorMessage?: string
  lastActiveAt?: string
  stoppedReason?: string
  mountedDatasets?: DatasetMountInfo[]
  createdAt: string
  updatedAt: string
}

export interface DevEnvironmentCreateParams {
  name: string
  environmentImageId: string
  gpuCount?: number
  cpu?: string
  memory?: string
  description?: string
  envVars?: Record<string, string>
  datasets?: { datasetId: string; versionId?: string }[]
}

export interface AccessUrlResponse {
  accessUrl: string
  message: string
}
