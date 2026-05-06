export interface Image {
  id: string
  name: string
  tag: string
  imageRef: string
  description?: string
  source: string
  isEnabled: boolean
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
