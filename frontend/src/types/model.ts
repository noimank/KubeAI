export interface DeployImageOption {
  imageId: string
  imageName?: string | null
  imageTag?: string | null
}

/** 模型版本部署配置 (响应形态): 候选镜像列表 + 部署参数, 部署为推理服务时作预填 */
export interface ModelDeployConfig {
  images?: DeployImageOption[]
  containerPort?: number | null
  subpathMode?: 'rewrite' | 'native' | null
  command?: string[] | null
  args?: string[] | null
  envVars?: Record<string, string> | null
  gpuCount?: number | null
  cpu?: string | null
  memory?: string | null
  replicas?: number | null
}

/** 部署配置提交形态: images → imageIds */
export interface ModelDeployConfigInput {
  imageIds?: string[]
  containerPort?: number
  subpathMode?: 'rewrite' | 'native'
  command?: string[]
  args?: string[]
  envVars?: Record<string, string>
  gpuCount?: number
  cpu?: string
  memory?: string
  replicas?: number
}

export interface ModelVersion {
  id: string
  registeredModelId: string
  versionNumber: number
  description?: string
  storagePath: string
  status: string
  fileCount: number
  totalSizeBytes: number
  trainingJobId?: string
  trainingJobName?: string
  datasetId?: string
  datasetName?: string
  datasetVersionId?: string
  datasetVersionNumber?: number
  imageId?: string
  imageName?: string
  imageTag?: string
  hyperparameters?: Record<string, string>
  deployConfig?: ModelDeployConfig | null
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
  deployConfig?: ModelDeployConfigInput
}

export interface ModelVersionFile {
  fileName: string
  sizeBytes: number
  contentType: string
  lastModified?: string
}
