import { api } from './api'
import type { BaseResponse } from '@/types/api'
import type { TokenPayload } from '@/types/auth'

export interface OAuthProvider {
  name: string
  displayName: string
}

export async function getOAuthProviders(): Promise<BaseResponse<OAuthProvider[]>> {
  const res = await api.get<BaseResponse<OAuthProvider[]>>('/auth/oauth/providers')
  return res.data
}

export async function oauthCallback(
  provider: string,
  code: string,
  state: string,
): Promise<BaseResponse<TokenPayload>> {
  const res = await api.post<BaseResponse<TokenPayload>>(`/auth/oauth/${provider}/callback`, {
    code,
    state,
  })
  return res.data
}
