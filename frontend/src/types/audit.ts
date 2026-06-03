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
  | 'add_member'
  | 'update_role'
  | 'remove_member'
  | 'update_quota'
  | 'transfer_quota'
  | 'upload'
  | 'build'
  | 'rebuild'
  | 'cleanup_job'
  | 'download'

export type ResourceType =
  | 'tenant'
  | 'user'
  | 'quota'
  | 'membership'
  | 'invitation'
  | 'credential'
  | 'dataset'
  | 'image'
  | 'dev_environment_image'
  | 'training_job'
  | 'model'
  | 'annotation_project'
  | 'algorithm'

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
  action?: AuditAction[]
  resourceType?: ResourceType[]
  username?: string
  userId?: string
  tenantId?: string
  startTime?: string
  endTime?: string
  page?: number
  pageSize?: number
}
