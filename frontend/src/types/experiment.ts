export interface Experiment {
  id: string
  tenantId: string
  trainingJobId: string
  trainingJobName: string | null
  mlflowExperimentId: string | null
  mlflowRunId: string | null
  status: 'active' | 'completed' | 'failed'
  hyperparameters: Record<string, string> | null
  metrics: Array<{ key: string; value: number }> | null
  datasetVersion: string | null
  imageName: string | null
  createdAt: string
  updatedAt: string
}

export interface MetricHistoryPoint {
  step: number
  value: number
  timestamp: number
}

export interface TrainingJobInfo {
  id: string
  name: string | null
  command: string | null
  datasetVersion: string | null
  imageName: string | null
  gpuCount: number | null
  cpu: string | null
  memory: string | null
  datasetId: string | null
  datasetVersionId: string | null
  imageId: string | null
  gpuMode: string | null
  workerCount: number | null
  priority: string | null
  mlflowEnabled: boolean | null
  tensorboardEnabled: boolean | null
  envVars: Record<string, string> | null
}

export interface ExperimentDetail extends Experiment {
  metricHistories: Record<string, MetricHistoryPoint[]> | null
  durationSeconds: number | null
  trainingJob: TrainingJobInfo | null
}

export interface HyperparamDiff {
  key: string
  values: Record<string, string | null>
  isDifferent: boolean
}

export interface MetricComparison {
  metricKey: string
  series: Record<string, MetricHistoryPoint[]>
}

export interface ExperimentComparison {
  experiments: Experiment[]
  hyperparamsDiff: HyperparamDiff[]
  metricsComparison: MetricComparison[]
}
