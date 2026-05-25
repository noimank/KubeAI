export interface DashboardResourceOverview {
  gpuUsed: number
  gpuTotal: number
  activeJobs: number
  activeDatasets: number
}

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

export interface TenantRankingItem {
  tenantId: string
  tenantName: string
  gpuQuota: number
  gpuUsed: number
  gpuUtilization: number
  cpuUtilization: number
  activeJobs: number
}

export interface RecentAlert {
  id: string
  type: string
  title: string
  priority: string
  createdAt: string
}

export interface ClusterOverviewBrief {
  gpuTotal: number
  gpuUsed: number
  gpuUtilization: number
  cpuTotal: number
  cpuUsed: number
  cpuUtilization: number
  memoryTotal: number
  memoryUsed: number
  memoryUtilization: number
}

export interface PendingAnnotationTask {
  id: string
  projectId: string
  projectName: string
  status: string
  totalTasks: number
  completedTasks: number
}

export interface AnnotationProgressOverview {
  pendingCount: number
  todayCompleted: number
  totalCompletionRate: number
}

export interface RecentInferenceService {
  id: string
  name: string
  status: string
  replicas: number
  endpointUrl?: string
}

export interface EngineerDashboard {
  resourceOverview: DashboardResourceOverview
  recentTrainingJobs: RecentTrainingJob[]
  recentDatasets: RecentDataset[]
}

export interface AdminDashboard {
  clusterOverview: ClusterOverviewBrief
  tenantRanking: TenantRankingItem[]
  recentAlerts: RecentAlert[]
}

export interface AnnotatorDashboard {
  progressOverview: AnnotationProgressOverview
  pendingTasks: PendingAnnotationTask[]
}

export interface MLOpsDashboard {
  resourceOverview: DashboardResourceOverview
  recentInferenceServices: RecentInferenceService[]
}

export interface DashboardResponse {
  role: string
  data: EngineerDashboard | AdminDashboard | AnnotatorDashboard | MLOpsDashboard
}
