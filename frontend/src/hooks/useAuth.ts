import { useAuthStore } from '@/stores/authStore'

export function useAuth() {
  const { user, isAuthenticated, accessToken, refreshToken, login, logout, setTokens, setUser } =
    useAuthStore()

  return {
    user,
    isAuthenticated,
    accessToken,
    refreshToken,
    login,
    logout,
    setTokens,
    setUser,
  }
}
