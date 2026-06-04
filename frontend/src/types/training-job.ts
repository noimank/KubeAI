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
  metricsPort?: number
  source?: string
  sourceEnvId?: string
  workspacePath?: string
  homePath?: string
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
  gpuCount?: number
  gpuMode?: string
  cpu?: string
  memory?: string
  priority?: string
  workerCount?: number
  metricsPort?: number
  sourceExperimentId?: string
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
export type { GpuMetricPoint, TimeSeriesPoint } from './metrics'
import type { GpuMetricPoint, TimeSeriesPoint } from './metrics'

export interface TrainingMetrics {
  gpuMetrics: GpuMetricPoint[]
  gpuUtilizationHistory: TimeSeriesPoint[]
  metricsUrl: string | null
  prometheusAvailable: boolean
  timestamp: string
}
