export type InferenceServiceStatus = 'pending' | 'deploying' | 'running' | 'failed' | 'stopped'

export type ScalingMode = 'fixed' | 'auto'
export type MetricType = 'concurrency' | 'cpu'
export type CanaryStatus = 'none' | 'deploying' | 'running' | 'failed'

export interface AutoScalingConfig {
  scalingMode: ScalingMode
  minReplicas: number
  maxReplicas: number
  targetMetricType?: MetricType
  targetMetricValue?: number
  cooldownPeriod: number
  pollingInterval: number
}

export interface AutoScalingUpdateRequest {
  scalingMode: ScalingMode
  minReplicas: number
  maxReplicas: number
  targetMetricType?: MetricType
  targetMetricValue?: number
  cooldownPeriod: number
  pollingInterval: number
}

export interface ModelVersionSummary {
  id: string
  versionNumber: number
  registeredModelId: string
  status: string
  storagePath?: string
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
  errorMessage?: string
  scalingMode: ScalingMode
  targetMetricType?: MetricType
  targetMetricValue?: number
  cooldownPeriod: number
  pollingInterval: number
  canaryStatus: CanaryStatus
  canaryModelVersionId?: string
  canaryTrafficPercent?: number
  canaryKserveName?: string
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
  autoScaling?: AutoScalingConfig
}

export interface InferenceServiceEvent {
  type: string
  reason: string
  message: string
  involvedObjectKind: string
  involvedObjectName: string
  count: number
  firstTimestamp: string | null
  lastTimestamp: string | null
}

export interface InferenceServiceScaleRequest {
  replicas: number
}

export interface CanaryStartRequest {
  canaryModelVersionId: string
  canaryTrafficPercent: number
}

export interface CanaryTrafficUpdateRequest {
  canaryTrafficPercent: number
}

export interface CanaryStatusResponse {
  canaryStatus: CanaryStatus
  canaryModelVersion?: ModelVersionSummary
  canaryTrafficPercent?: number
  stableTrafficPercent?: number
  canaryEndpointUrl?: string
  canaryEvents: InferenceServiceEvent[]
}
