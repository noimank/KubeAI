export type AnnotationProjectStatus =
  | 'draft'
  | 'pending'
  | 'active'
  | 'completed'
  | 'failed'
  | 'archived'

export interface AnnotationProject {
  id: string
  name: string
  description?: string
  datasetId: string
  datasetVersionId: string
  templateId?: string | null
  templateName?: string | null
  labelStudioProjectId?: number
  totalTasks: number
  completedTasks: number
  status: AnnotationProjectStatus
  createdBy: string
  createdAt: string
  updatedAt: string
  tenantId: string
  datasetName?: string
  datasetVersionNumber?: number
  progressPercent: number
}

export interface AnnotationProjectDetail extends AnnotationProject {
  labelConfig?: string | null
  labelingTemplateDescription?: string
}

export interface AnnotationProjectCreateRequest {
  name: string
  description?: string
  datasetId: string
  datasetVersionId: string
  templateId: string
}

export type AnnotationTaskStatus = 'unassigned' | 'assigned' | 'in_progress' | 'completed'

export interface AnnotationTask {
  id: string
  projectId: string
  labelStudioTaskId: number
  data: Record<string, unknown>
  assignedTo?: string
  assignedToName?: string
  status: AnnotationTaskStatus
  result?: AnnotationResultItem[] | null
  projectName?: string
  templateName?: string | null
  submittedAt?: string | null
  submittedBy?: string | null
  annotationPayload?: Record<string, unknown> | null
  createdAt: string
  updatedAt: string
}

export interface AnnotationTaskAssignRequest {
  taskIds: string[]
  userId: string
}

export interface AnnotationTaskUnassignRequest {
  taskIds: string[]
}

export interface AnnotationBatchAssignRequest {
  userIds: string[]
  tasksPerUser: number
}

export interface AnnotationTaskSummary {
  projectId: string
  projectName: string
  templateName: string
  totalTasks: number
  assignedTasks: number
  completedTasks: number
}

export interface AnnotationResultItem {
  /** 区域 ID（多个 result 共享同一 ID 表示属于同一空间区域） */
  id?: string
  from_name: string
  to_name: string
  type: string
  value: Record<string, unknown>
}

export interface AnnotationSubmitRequest {
  result: AnnotationResultItem[]
}
