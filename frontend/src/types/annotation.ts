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
