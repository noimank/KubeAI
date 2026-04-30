export type UserRole = 'admin' | 'mlops' | 'engineer' | 'annotator'

export interface User {
  id: string
  username: string
  email: string
  role: UserRole
  isActive: boolean
  authProvider: string
  tenantId?: string
  tenantName?: string
  createdAt: string
  updatedAt: string
}

export interface UserDetail extends User {
  failedLoginAttempts: number
  lockedUntil?: string
}

export interface UserListResponse {
  items: User[]
  total: number
  page: number
  pageSize: number
}

export interface UserUpdateRequest {
  role?: UserRole
  tenantId?: string | null
}

export interface UserStatusToggleRequest {
  isActive: boolean
}
