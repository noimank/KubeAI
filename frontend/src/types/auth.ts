export type UserRole = 'admin' | 'mlops' | 'engineer' | 'annotator'

export interface User {
  id: string
  username: string
  email: string
  nickname?: string
  avatar?: string
  role: UserRole
  authProvider: string
  tenantId?: string
}

export interface TokenPayload {
  accessToken: string
  refreshToken: string
  tokenType: string
}

export interface AuthConfig {
  allowUserRegistration: boolean
  oidcAutoRedirect: boolean
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
  confirmPassword: string
}
