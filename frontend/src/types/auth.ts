export type UserRole = 'admin' | 'mlops' | 'engineer' | 'annotator'

export interface User {
  id: string
  username: string
  email: string
  role: UserRole
  tenant_id: string
  avatar?: string
}

export interface TokenPayload {
  access_token: string
  refresh_token: string
  token_type: string
}

export interface RegisterRequest {
  username: string
  email: string
  password: string
  confirm_password: string
}
