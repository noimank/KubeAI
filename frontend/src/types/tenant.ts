export interface Tenant {
  id: string
  name: string
  displayName: string
  description?: string
  status: 'active' | 'disabled'
  k8sNamespaceName?: string
  createdAt: string
  updatedAt: string
}
