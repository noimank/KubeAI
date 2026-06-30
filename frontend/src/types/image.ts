export type BuildStatus = 'pending' | 'building' | 'pushing' | 'succeeded' | 'failed'
export type ImageCategory = 'training' | 'inference' | 'other'

export interface Image {
  id: string
  name: string
  tag: string
  imageRef: string
  description?: string
  source: string
  category: ImageCategory
  isEnabled: boolean
  tenantId?: string
  buildStatus?: BuildStatus
  dockerfile?: string
  createdAt: string
  updatedAt: string
}

export interface ImageCreateParams {
  name: string
  tag: string
  imageRef: string
  description?: string
  category?: ImageCategory
}

export interface ImageUpdateParams {
  name?: string
  tag?: string
  imageRef?: string
  description?: string
  category?: ImageCategory
}

export interface ImageBuildParams {
  dockerfile: string
  name: string
  tag: string
  description?: string
  category?: ImageCategory
}

export interface ImageBuildLog {
  buildStatus?: BuildStatus
  log: string
}

export interface ImageSelectable {
  id: string
  name: string
  tag: string
  imageRef: string
  source: string
  category: ImageCategory
}
