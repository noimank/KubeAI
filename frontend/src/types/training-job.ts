export type TrainingJobStatus =
  | 'pending'
  | 'queued'
  | 'initializing'
  | 'running'
  | 'succeeded'
  | 'failed'
  | 'stopped'

export interface Hyperparameter {
  key: string
  value: string
}

export interface TrainingJob {
  id: string
  tenantId: string
  name: string
  description?: string
  createdBy: string
  datasetId?: string
  datasetVersionId?: string
  imageId: string
  command: string
  hyperparameters?: Record<string, string>
  envVars?: Record<string, string>
  gpuCount: number
  gpuMode: string
  cpu: string
  memory: string
  priority: string
  workerCount: number
  status: TrainingJobStatus
  vcjobName?: string
  startedAt?: string
  finishedAt?: string
  errorMessage?: string
  source?: string
  sourceEnvId?: string
  workspacePath?: string
  homePath?: string
  mlflowEnabled: boolean
  tensorboardEnabled: boolean
  experimentId?: string
  createdAt: string
  updatedAt: string
}

export interface TrainingJobCreate {
  name: string
  description?: string
  datasetId?: string
  datasetVersionId?: string
  imageId: string
  command: string
  hyperparameters?: Hyperparameter[]
  envVars?: Record<string, string>
  gpuCount?: number
  gpuMode?: string
  cpu?: string
  memory?: string
  priority?: string
  workerCount?: number
  sourceExperimentId?: string
  mlflowEnabled?: boolean
  tensorboardEnabled?: boolean
}

/** 从开发环境发起训练: 镜像可留空由后端按环境镜像解析, 资源缺省继承环境配置 */
export interface TrainingJobFromEnvironmentCreate extends Omit<
  TrainingJobCreate,
  'imageId' | 'sourceExperimentId'
> {
  environmentId: string
  imageId?: string
}

export interface PodInfo {
  podName: string
  role: string
  status: string
}

export interface LogData {
  lines: string[]
  hasMore: boolean
  totalLines: number
}

// Re-export shared GPU metric types
import type { GpuMetricPoint, TimeSeriesPoint } from './metrics'

export interface TrainingMetrics {
  gpuMetrics: GpuMetricPoint[]
  gpuUtilizationHistory: TimeSeriesPoint[]
  metricsUrl: string | null
  prometheusAvailable: boolean
  timestamp: string
}
