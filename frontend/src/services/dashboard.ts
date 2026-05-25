import { api } from './api'
import type { BaseResponse } from '@/types/api'
import type { DashboardResponse } from '@/types/dashboard'

export async function getDashboard(): Promise<BaseResponse<DashboardResponse>> {
  const res = await api.get<BaseResponse<DashboardResponse>>('/dashboard')
  return res.data
}
