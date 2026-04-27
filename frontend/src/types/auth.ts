export interface User {
  id: string
  username: string
  email: string
  role: string
  tenant_id: string
  avatar?: string
}

export interface TokenPayload {
  access_token: string
  refresh_token: string
  token_type: string
}
