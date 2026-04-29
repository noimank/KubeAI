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

export type InvitationStatus = 'pending' | 'accepted' | 'cancelled' | 'expired'

export interface Invitation {
  id: string
  tenantId: string
  email: string
  role: string
  token: string
  status: InvitationStatus
  invitedBy: string
  expiresAt: string
  createdAt: string
}

export interface InvitationCreateRequest {
  email: string
  role: string
}

export interface TenantMember {
  id: string
  username: string
  email: string
  role: string
  isActive: boolean
  joinedAt: string
}

export interface UpdateMemberRoleRequest {
  role: string
}

export interface AcceptInvitationRequest {
  token: string
  username?: string
  password?: string
  confirmPassword?: string
  force?: boolean
}

export interface InvitationInfo {
  tenantName: string
  tenantDisplayName: string
  email: string
  role: string
}
