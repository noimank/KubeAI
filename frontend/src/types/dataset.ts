export interface DatasetVersion {
  id: string
  datasetId: string
  versionNumber: number
  description?: string
  storagePath: string
  fileCount: number
  totalSizeBytes: number
  createdBy: string
  createdAt: string
}

export interface Dataset {
  id: string
  name: string
  description?: string
  tenantId: string
  createdBy: string
  createdByName?: string
  versionCount: number
  totalFileCount: number
  totalSizeBytes: number
  latestVersion?: DatasetVersion
  createdAt: string
  updatedAt: string
}
