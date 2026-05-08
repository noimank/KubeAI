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
  status: TrainingJobStatus
  vcjobName?: string
  startedAt?: string
  finishedAt?: string
  errorMessage?: string
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
}
