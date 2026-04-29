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
