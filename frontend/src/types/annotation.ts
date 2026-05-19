export type AnnotationType =
  | 'image_classification'
  | 'object_detection'
  | 'image_segmentation'
  | 'text_classification'

export type AnnotationProjectStatus = 'draft' | 'active' | 'completed' | 'archived'

export interface AnnotationProject {
  id: string
  name: string
  description?: string
  datasetId: string
  datasetVersionId: string
  annotationType: AnnotationType
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
  labelConfig: string
  labelingTemplateDescription?: string
}

export interface AnnotationTemplate {
  key: AnnotationType
  label: string
  description: string
}

export interface AnnotationProjectCreateRequest {
  name: string
  description?: string
  datasetId: string
  datasetVersionId: string
  annotationType: AnnotationType
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
  projectName?: string
  annotationType?: AnnotationType
  createdAt: string
  updatedAt: string
}

export interface AnnotationTaskAssignRequest {
  taskIds: string[]
  userId: string
}

export interface AnnotationBatchAssignRequest {
  userIds: string[]
  tasksPerUser: number
}

export interface AnnotationTaskSummary {
  projectId: string
  projectName: string
  annotationType: AnnotationType
  totalTasks: number
  assignedTasks: number
  completedTasks: number
}
