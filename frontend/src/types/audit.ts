export type AuditAction =
  | 'create'
  | 'update'
  | 'delete'
  | 'login'
  | 'logout'
  | 'register'
  | 'enable'
  | 'disable'
  | 'invite'
  | 'accept_invite'
  | 'cancel_invite'
  | 'update_role'
  | 'remove_member'
  | 'update_quota'

export type ResourceType = 'tenant' | 'user' | 'quota' | 'membership' | 'invitation' | 'credential'

export interface AuditLog {
  id: string
  userId?: string
  username?: string
  tenantId?: string
  action: AuditAction
  resourceType: ResourceType
  resourceId?: string
  detail?: Record<string, unknown>
  ipAddress: string
  userAgent?: string
  requestId?: string
  createdAt: string
}

export interface AuditLogQueryParams {
  action?: AuditAction
  resourceType?: ResourceType
  userId?: string
  tenantId?: string
  startTime?: string
  endTime?: string
  page?: number
  pageSize?: number
}
