import { api } from './api'
import type { BaseResponse } from '@/types/api'
import type { AuthConfig, RegisterRequest, TokenPayload, User } from '@/types/auth'
import type { AcceptInvitationRequest, InvitationInfo } from '@/types/tenant'

export async function getAuthConfig(): Promise<BaseResponse<AuthConfig>> {
  const res = await api.get<BaseResponse<AuthConfig>>('/auth/config')
  return res.data
}

export async function register(data: RegisterRequest): Promise<BaseResponse<TokenPayload>> {
  const res = await api.post<BaseResponse<TokenPayload>>('/auth/register', data)
  return res.data
}

export async function login(
  username: string,
  password: string,
): Promise<BaseResponse<TokenPayload>> {
  const res = await api.post<BaseResponse<TokenPayload>>('/auth/login', { username, password })
  return res.data
}

export async function getCurrentUser(): Promise<BaseResponse<User>> {
  const res = await api.get<BaseResponse<User>>('/auth/me')
  return res.data
}

export async function getInvitationInfo(token: string): Promise<BaseResponse<InvitationInfo>> {
  const res = await api.get<BaseResponse<InvitationInfo>>('/auth/invitation-info', {
    params: { token },
  })
  return res.data
}

export async function acceptInvitation(
  data: AcceptInvitationRequest,
): Promise<BaseResponse<TokenPayload>> {
  const res = await api.post<BaseResponse<TokenPayload>>('/auth/accept-invitation', data)
  return res.data
}
