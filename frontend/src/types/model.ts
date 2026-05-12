export interface ModelVersion {
  id: string
  registeredModelId: string
  versionNumber: number
  description?: string
  storagePath: string
  fileCount: number
  totalSizeBytes: number
  trainingJobId?: string
  datasetId?: string
  datasetVersionId?: string
  imageId?: string
  hyperparameters?: Record<string, string>
  createdBy: string
  createdAt: string
}

export interface RegisteredModel {
  id: string
  name: string
  description?: string
  tenantId: string
  createdBy: string
  createdByName?: string
  versionCount: number
  latestVersion?: ModelVersion
  createdAt: string
  updatedAt: string
}

export interface RegisteredModelDetail extends RegisteredModel {
  versions: ModelVersion[]
}

export interface ModelVersionCreate {
  name: string
  description?: string
  filePaths: string[]
  trainingJobId?: string
}
