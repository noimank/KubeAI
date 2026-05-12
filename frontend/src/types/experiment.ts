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
