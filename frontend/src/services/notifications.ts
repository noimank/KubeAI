import { api } from './api'
import type { PageResponse } from '@/types/api'
import type {
  Notification,
  NotificationListParams,
  UnreadCountResponse,
} from '@/types/notification'

export async function getNotifications(
  params?: NotificationListParams,
): Promise<PageResponse<Notification>> {
  const res = await api.get<PageResponse<Notification>>('/notifications', {
    params: {
      page: params?.current,
      page_size: params?.pageSize,
      type: params?.type,
    },
  })
  return res.data
}

export async function getUnreadCount(): Promise<UnreadCountResponse> {
  const res = await api.get<{ success: boolean; message: string; data: UnreadCountResponse }>(
    '/notifications/unread-count',
  )
  return res.data.data!
}

export async function markAsRead(id: string): Promise<void> {
  await api.post(`/notifications/${id}/read`)
}

export async function markAllAsRead(): Promise<void> {
  await api.post('/notifications/read-all')
}
