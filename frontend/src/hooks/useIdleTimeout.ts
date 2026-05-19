import { useEffect } from 'react'

import { useAuthStore } from '@/stores/authStore'
import { getMessageInstance } from '@/utils/messageHolder'

const IDLE_TIMEOUT = parseInt(import.meta.env.VITE_IDLE_TIMEOUT_MINUTES || '30') * 60 * 1000

const ACTIVITY_EVENTS = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart']

export function useIdleTimeout() {
  const logout = useAuthStore((state) => state.logout)
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated)

  useEffect(() => {
    if (!isAuthenticated) return

    let timeoutId: ReturnType<typeof setTimeout>

    const resetTimer = () => {
      clearTimeout(timeoutId)
      timeoutId = setTimeout(() => {
        logout()
        getMessageInstance()?.warning('已空闲超时，请重新登录')
      }, IDLE_TIMEOUT)
    }

    ACTIVITY_EVENTS.forEach((event) => window.addEventListener(event, resetTimer))
    resetTimer()

    return () => {
      clearTimeout(timeoutId)
      ACTIVITY_EVENTS.forEach((event) => window.removeEventListener(event, resetTimer))
    }
  }, [logout, isAuthenticated])
}
