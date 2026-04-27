export interface Tenant {
  id: string
  name: string
  display_name: string
  description?: string
  status: 'active' | 'disabled'
  created_at: string
  updated_at: string
}
