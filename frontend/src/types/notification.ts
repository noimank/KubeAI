export type NotificationType =
  | 'training_job'
  | 'quota_alert'
  | 'annotation_task'
  | 'inference_service'
export type NotificationPriority = 'low' | 'medium' | 'high'

export interface Notification {
  id: string
  userId: string
  tenantId: string
  type: NotificationType
  title: string
  content: string
  priority: NotificationPriority
  isRead: boolean
  resourceType?: string
  resourceId?: string
  createdAt: string
}

export interface NotificationListParams {
  current: number
  pageSize: number
  type?: NotificationType
  unread?: boolean
}

export interface UnreadCountResponse {
  count: number
}
