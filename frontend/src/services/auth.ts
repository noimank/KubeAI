import { api } from './api'
import type { BaseResponse } from '@/types/api'
import type { User, TokenPayload } from '@/types/auth'

export async function login(
  username: string,
  password: string,
): Promise<BaseResponse<TokenPayload>> {
  const res = await api.post<BaseResponse<TokenPayload>>('/auth/login', { username, password })
  return res.data
}

export async function refreshToken(refreshToken: string): Promise<BaseResponse<TokenPayload>> {
  const res = await api.post<BaseResponse<TokenPayload>>('/auth/refresh', { refreshToken })
  return res.data
}

export async function getCurrentUser(): Promise<BaseResponse<User>> {
  const res = await api.get<BaseResponse<User>>('/auth/me')
  return res.data
}

export async function logout(): Promise<BaseResponse<null>> {
  const res = await api.post<BaseResponse<null>>('/auth/logout')
  return res.data
}
