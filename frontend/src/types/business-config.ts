export interface BusinessConfig {
  id: string
  tenantId: string
  createdBy: string
  name: string
  description?: string
  envVars: Record<string, string>
  createdAt: string
  updatedAt: string
}

export interface BusinessConfigCreate {
  name: string
  description?: string
  envVars: Record<string, string>
}

export interface BusinessConfigUpdate {
  name?: string
  description?: string
  envVars?: Record<string, string>
}
