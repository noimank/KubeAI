import { api } from './api'
import type { BaseResponse, PageResponse } from '@/types/api'
import type { AuditLog, AuditLogQueryParams } from '@/types/audit'

export async function getAuditLogs(params?: AuditLogQueryParams): Promise<PageResponse<AuditLog>> {
  const res = await api.get<PageResponse<AuditLog>>('/audit-logs', {
    params: {
      page: params?.page,
      page_size: params?.pageSize,
      action: params?.action,
      resource_type: params?.resourceType,
      username: params?.username,
      start_time: params?.startTime,
      end_time: params?.endTime,
    },
    paramsSerializer: {
      indexes: null,
    },
  })
  return res.data
}

export async function getAuditLog(id: string): Promise<BaseResponse<AuditLog>> {
  const res = await api.get<BaseResponse<AuditLog>>(`/audit-logs/${id}`)
  return res.data
}
