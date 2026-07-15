export interface AnnotationTemplate {
  id: string
  name: string
  description?: string | null
  tags: string[]
  group: string
  createdBy: string
  createdAt: string
  updatedAt: string
}

export interface AnnotationTemplateDetail extends AnnotationTemplate {
  labelConfig: string
  projectCount: number
}

export interface AnnotationTemplateImportItem {
  key: string
  label: string
  description: string
  config: string
  group: string
}

export interface AnnotationTemplateCreateRequest {
  name: string
  description?: string
  labelConfig: string
  tags: string[]
  group: string
}

export interface AnnotationTemplateUpdateRequest {
  name?: string
  description?: string
  labelConfig?: string
  tags?: string[]
  group?: string
}
