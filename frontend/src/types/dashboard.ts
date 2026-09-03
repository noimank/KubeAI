export interface RecentTrainingJob {
  id: string
  name: string
  status: string
  gpuCount: number
  createdAt: string
}

export interface RecentDataset {
  id: string
  name: string
  displayName?: string
  versionCount: number
  fileCount: number
  updatedAt?: string
}

export interface RecentInferenceService {
  id: string
  name: string
  status: string
  replicas: number
  endpointUrl?: string
}

export interface PendingAnnotationProject {
  projectId: string
  projectName: string
  totalTasks: number
  completedTasks: number
}

export interface DashboardResponse {
  recentTrainingJobs: RecentTrainingJob[] | null
  recentDatasets: RecentDataset[] | null
  recentInferenceServices: RecentInferenceService[] | null
  pendingAnnotations: PendingAnnotationProject[] | null
}
