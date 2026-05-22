import { create } from 'zustand'
import type { User } from '@/types/auth'
import { useRbacStore } from './rbacStore'
import { useTenantStore } from './tenantStore'
import { useNotificationStore } from './notificationStore'
import { getCurrentUser } from '@/services/auth'

export const ACCESS_TOKEN_KEY = 'kubeai_access_token'
export const REFRESH_TOKEN_KEY = 'kubeai_refresh_token'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isInitializing: boolean
  login: (user: User, accessToken: string, refreshToken: string) => void
  logout: () => void
  setTokens: (accessToken: string, refreshToken: string) => void
  setUser: (user: User) => void
  initializeAuth: () => Promise<void>
}

function getStoredToken(key: string): string | null {
  return localStorage.getItem(key)
}

async function callLogoutApi() {
  const accessToken = localStorage.getItem(ACCESS_TOKEN_KEY)
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY)
  if (!accessToken) return

  try {
    const axios = (await import('axios')).default
    await axios.post(
      `${import.meta.env.VITE_API_BASE_URL || '/api'}/auth/logout`,
      { refresh_token: refreshToken || undefined },
      { headers: { Authorization: `Bearer ${accessToken}` } },
    )
  } catch {
    // best-effort: network failure should not block local cleanup
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  accessToken: getStoredToken(ACCESS_TOKEN_KEY),
  refreshToken: getStoredToken(REFRESH_TOKEN_KEY),
  isAuthenticated: !!getStoredToken(ACCESS_TOKEN_KEY),
  isInitializing: !!getStoredToken(ACCESS_TOKEN_KEY),

  login: (user, accessToken, refreshToken) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
    useRbacStore.getState().setRole(user.role)
    set({ user, accessToken, refreshToken, isAuthenticated: true })

    if (user.tenantId) {
      useTenantStore.getState().fetchCurrentTenant()
    }

    useNotificationStore.getState().fetchUnreadCount()
  },

  logout: () => {
    callLogoutApi()
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    useRbacStore.getState().clearRbac()
    useTenantStore.getState().clearTenant()
    set({ user: null, accessToken: null, refreshToken: null, isAuthenticated: false })
  },

  setTokens: (accessToken, refreshToken) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
    set({ accessToken, refreshToken })
  },

  setUser: (user) => {
    useRbacStore.getState().setRole(user.role)
    set({ user })
  },

  initializeAuth: async () => {
    const token = getStoredToken(ACCESS_TOKEN_KEY)
    if (!token) return
    set({ isInitializing: true })
    try {
      const res = await getCurrentUser()
      if (res.success && res.data) {
        useRbacStore.getState().setRole(res.data.role)
        if (res.data.tenantId) {
          useTenantStore.getState().fetchCurrentTenant()
        }
        set({ user: res.data, isAuthenticated: true, isInitializing: false })
      } else {
        set({ isInitializing: false })
      }
    } catch {
      set({ isInitializing: false })
    }
  },
}))
