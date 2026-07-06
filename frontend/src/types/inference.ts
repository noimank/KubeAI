export type InferenceServiceStatus = 'pending' | 'deploying' | 'running' | 'failed' | 'stopped'
export type ScalingMode = 'fixed' | 'auto'
export type SubpathMode = 'rewrite' | 'native'
export type MetricType = 'gpu' | 'cpu'

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

export interface InferenceService {
  id: string
  tenantId: string
  createdBy: string
  name: string
  modelVersionId?: string
  image?: string
  containerPort?: number
  command?: string
  args?: string
  gpuCount: number
  cpu: string
  memory: string
  replicas: number
  minReplicas: number
  maxReplicas: number
  status: InferenceServiceStatus
  endpointUrl?: string
  proxyEndpoint?: string
  hasToken: boolean
  description?: string
  envVars?: Record<string, string>
  errorMessage?: string
  scalingMode: ScalingMode
  subpathMode?: SubpathMode
  targetMetricType?: MetricType
  targetMetricValue?: number
  cooldownPeriod: number
  pollingInterval: number
  modelVersion?: ModelVersionSummary
  createdAt: string
  updatedAt: string
}

export interface ModelVersionSummary {
  id: string
  versionNumber: number
  registeredModelId: string
  modelName: string
  status: string
}

export interface InferenceServiceCreate {
  name: string
  gpuCount?: number
  cpu?: string
  memory?: string
  replicas?: number
  image?: string
  imageId?: string
  modelVersionId?: string
  containerPort?: number
  command?: string[]
  args?: string[]
  envVars?: Record<string, string>
  description?: string
  autoScaling?: AutoScalingConfig
  subpathMode?: SubpathMode
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

// Re-export shared GPU metric types
import type { GpuMetricPoint, TimeSeriesPoint } from './metrics'

export interface InferenceServiceMetrics {
  gpuMetrics: GpuMetricPoint[]
  gpuUtilizationHistory: TimeSeriesPoint[]
  metricsUrl: string | null
  prometheusAvailable: boolean
  timestamp: string
}
