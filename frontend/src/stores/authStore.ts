import { create } from 'zustand'
import type { User } from '@/types/auth'
import { useRbacStore } from './rbacStore'

const ACCESS_TOKEN_KEY = 'kubeai_access_token'
const REFRESH_TOKEN_KEY = 'kubeai_refresh_token'

interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  login: (user: User, accessToken: string, refreshToken: string) => void
  logout: () => void
  setTokens: (accessToken: string, refreshToken: string) => void
  setUser: (user: User) => void
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

  login: (user, accessToken, refreshToken) => {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken)
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken)
    useRbacStore.getState().setRole(user.role)
    set({ user, accessToken, refreshToken, isAuthenticated: true })
  },

  logout: () => {
    callLogoutApi()
    localStorage.removeItem(ACCESS_TOKEN_KEY)
    localStorage.removeItem(REFRESH_TOKEN_KEY)
    useRbacStore.getState().clearRbac()
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
}))
