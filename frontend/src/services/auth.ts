import { api } from './api'
import type { BaseResponse } from '@/types/api'
import type { RegisterRequest, TokenPayload, User } from '@/types/auth'

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
