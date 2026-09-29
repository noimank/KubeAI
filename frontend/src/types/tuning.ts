export type SearchSpaceParamType = 'float' | 'int' | 'categorical' | 'fixed'
export type TuningDirection = 'minimize' | 'maximize'
export type TuningStudyStatus = 'running' | 'completed' | 'stopped' | 'failed' | 'paused'
export type TuningTrialState = 'pending' | 'running' | 'complete' | 'failed' | 'pruned'
export type SamplerType = 'tpe' | 'cmaes' | 'random'

export interface SearchSpaceItem {
  type: SearchSpaceParamType
  low?: number
  high?: number
  log?: boolean
  step?: number
  choices?: string[]
  value?: number | string | boolean
}

export interface TuningStudy {
  id: string
  tenantId: string
  name: string
  description?: string
  createdBy: string
  status: TuningStudyStatus
  direction: TuningDirection
  metricName: string
  nTrials: number
  nJobs: number
  searchSpace: Record<string, SearchSpaceItem>
  imageId: string
  datasetId?: string
  datasetVersionId?: string
  command: string
  gpuCount: number
  gpuMode: string
  cpu: string
  memory: string
  priority: string
  workerCount: number
  envVars?: Record<string, string>
  optunaStudyName: string
  bestValue?: number
  pruningEnabled: boolean
  pruningConfig?: PruningConfig
  samplerConfig?: SamplerConfig
  stoppingConfig?: StoppingConfig
  errorMessage?: string
  createdAt: string
  updatedAt: string
  trialCount: number
  finalizedCount: number
  runningCount: number
}

export interface TuningTrial {
  id: string
  studyId: string
  trialNumber: number
  trainingJobId?: string
  params?: Record<string, unknown>
  state: TuningTrialState
  value?: number
  errorMessage?: string
  createdAt: string
  updatedAt: string
  jobName?: string
  jobStatus?: string
  /** trial 训练任务关联的实验 (用于实验详情入口与跨 trial 对比) */
  experimentId?: string
}

export interface TuningStudyCreate {
  name: string
  description?: string
  direction: TuningDirection
  metricName: string
  nTrials: number
  nJobs: number
  searchSpace: Record<string, SearchSpaceItem>
  imageId: string
  datasetId?: string
  datasetVersionId?: string
  command: string
  gpuCount?: number
  gpuMode?: string
  cpu?: string
  memory?: string
  priority?: string
  workerCount?: number
  envVars?: Record<string, string>
  pruningEnabled?: boolean
  pruningConfig?: PruningConfig
  samplerConfig?: SamplerConfig
  stoppingConfig?: StoppingConfig
}

export interface PruningConfig {
  nStartupTrials?: number
  nWarmupSteps?: number
  interval?: number
  nMinTrials?: number
  prunePercentile?: number
}

/** 采样器配置 (搜索策略). multivariate / nStartupTrials 仅对 tpe 生效. */
export interface SamplerConfig {
  type: SamplerType
  seed?: number
  multivariate?: boolean
  nStartupTrials?: number
}

/** 终止条件配置. 三者均可独立为空. */
export interface StoppingConfig {
  studyTimeoutSeconds?: number
  trialTimeoutSeconds?: number
  earlyStopPatience?: number
}

export interface BestTrial {
  studyId: string
  trialNumber?: number
  trainingJobId?: string
  params?: Record<string, unknown>
  value?: number
}

export type TuningTrialInsightState = 'complete' | 'failed' | 'pruned' | 'running' | 'pending'

export interface TuningTrialPoint {
  trialNumber: number
  value?: number
  params: Record<string, unknown>
  state: TuningTrialInsightState
  datetimeStart?: string
  datetimeComplete?: string
  durationSeconds?: number
}

export interface TuningInsights {
  history: TuningTrialPoint[]
  importance: Record<string, number>
}
