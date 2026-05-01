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

export interface DatasetDetail extends Dataset {
  versions: DatasetVersion[]
}

export interface VersionFile {
  fileName: string
  sizeBytes: number
  contentType: string
  lastModified: string
}

export interface FileTypeDistribution {
  extension: string
  count: number
  totalSizeBytes: number
}

export interface VersionStats {
  versionId: string
  versionNumber: number
  fileCount: number
  totalSizeBytes: number
  fileTypeDistribution: FileTypeDistribution[]
}

export interface DatasetMountInfo {
  pvcName: string
  mountPath: string
  accessMode: string
  storageRequest: string
  pvcStatus: string
}
