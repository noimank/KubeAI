import { api } from './api'
import type { BaseResponse, PageResponse } from '@/types/api'
import type { UserDetail, UserStatusToggleRequest, UserUpdateRequest } from '@/types/user'

export async function getUsers(
  page: number = 1,
  pageSize: number = 20,
  username?: string,
  email?: string,
  role?: string,
  isActive?: boolean,
  startTime?: string,
  endTime?: string,
): Promise<PageResponse<UserDetail>> {
  const res = await api.get<PageResponse<UserDetail>>('/users', {
    params: { page, pageSize, username, email, role, isActive, startTime, endTime },
  })
  return res.data
}

export async function getUser(id: string): Promise<BaseResponse<UserDetail>> {
  const res = await api.get<BaseResponse<UserDetail>>(`/users/${id}`)
  return res.data
}

export async function updateUser(
  id: string,
  data: UserUpdateRequest,
): Promise<BaseResponse<UserDetail>> {
  const res = await api.put<BaseResponse<UserDetail>>(`/users/${id}`, data)
  return res.data
}

export async function toggleUserStatus(
  id: string,
  data: UserStatusToggleRequest,
): Promise<BaseResponse<UserDetail>> {
  const res = await api.patch<BaseResponse<UserDetail>>(`/users/${id}/status`, data)
  return res.data
}

export async function deleteUser(id: string): Promise<BaseResponse<null>> {
  const res = await api.delete<BaseResponse<null>>(`/users/${id}`)
  return res.data
}
