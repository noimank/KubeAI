export type BuildStatus = 'pending' | 'building' | 'pushing' | 'succeeded' | 'failed'

export interface Image {
  id: string
  name: string
  tag: string
  imageRef: string
  description?: string
  source: string
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
}

export interface ImageUpdateParams {
  name?: string
  tag?: string
  imageRef?: string
  description?: string
}

export interface ImageBuildParams {
  dockerfile: string
  name: string
  tag: string
  description?: string
}

export interface ImageBuildLog {
  buildStatus?: BuildStatus
  log: string
}
