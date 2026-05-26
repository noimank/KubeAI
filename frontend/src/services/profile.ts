import { api } from './api'
import type { BaseResponse } from '@/types/api'
import type { User } from '@/types/auth'

export async function updateProfile(data: {
  nickname?: string
  email?: string
}): Promise<BaseResponse<User>> {
  const res = await api.patch<BaseResponse<User>>('/auth/me/profile', data)
  return res.data
}

export async function uploadAvatar(file: File): Promise<BaseResponse<User>> {
  const formData = new FormData()
  formData.append('file', file)
  const res = await api.post<BaseResponse<User>>('/auth/me/avatar', formData)
  return res.data
}

export async function changePassword(data: {
  currentPassword: string
  newPassword: string
  confirmPassword: string
}): Promise<BaseResponse<null>> {
  const res = await api.post<BaseResponse<null>>('/auth/me/password', data)
  return res.data
}
