import { create } from 'zustand'
import { getUnreadCount } from '@/services/notifications'

interface NotificationState {
  unreadCount: number
  fetchUnreadCount: () => Promise<void>
  decrementUnread: () => void
  clearUnread: () => void
}

export const useNotificationStore = create<NotificationState>((set) => ({
  unreadCount: 0,

  fetchUnreadCount: async () => {
    try {
      const data = await getUnreadCount()
      set({ unreadCount: data.count })
    } catch {
      // Silently fail — unread count is non-critical
    }
  },

  decrementUnread: () => set((s) => ({ unreadCount: Math.max(0, s.unreadCount - 1) })),

  clearUnread: () => set({ unreadCount: 0 }),
}))
