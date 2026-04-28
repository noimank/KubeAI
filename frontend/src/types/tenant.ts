export interface Tenant {
  id: string
  name: string
  display_name: string
  description?: string
  status: 'active' | 'disabled'
  k8s_namespace_name?: string
  created_at: string
  updated_at: string
}
