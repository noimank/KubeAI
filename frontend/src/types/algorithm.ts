export interface Algorithm {
  id: string
  name: string
  description: string | null
  tags: string[]
  sourceType: string
  sizeBytes: number | null
  status: string
  visibility: string
  uploader: {
    id: string
    username: string
  } | null
  createdAt: string
  updatedAt: string
}

export interface AlgorithmDetail extends Algorithm {
  minioObjectKey: string | null
}

export interface AlgorithmCreateParams {
  name: string
  description?: string
  tags?: string
  file: File
}

export interface AlgorithmRegisterParams {
  name: string
  description?: string
  tags?: string[]
  filePaths: string[]
}

export interface AlgorithmUpdateParams {
  name?: string
  description?: string
  tags?: string[]
}
