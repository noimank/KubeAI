export interface Tenant {
  id: string
  name: string
  displayName: string
  description?: string
  status: 'active' | 'disabled'
  k8sNamespaceName?: string
  gpuLimit: number
  cpuLimit: string
  memoryLimit: string
  storageLimit: string
  memberCount: number
  createdAt: string
  updatedAt: string
}

export interface TenantCreateRequest {
  name: string
  displayName: string
  description?: string
}

export interface TenantUpdateRequest {
  displayName?: string
  description?: string
}

export interface TenantQuotaUpdateRequest {
  gpuLimit: number
  cpuLimit: string
  memoryLimit: string
  storageLimit: string
  force?: boolean
}

export interface QuotaUsage {
  gpuUsed: number
  cpuUsed: string
  memoryUsed: string
  storageUsed: string
}
