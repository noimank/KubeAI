import { describe, it, expect, beforeEach, vi } from 'vitest'
import { useAuthStore } from '@/stores/authStore'
import { useRbacStore } from '@/stores/rbacStore'

vi.mock('@/services/auth', () => ({
  getCurrentUser: vi.fn(),
}))

import { getCurrentUser } from '@/services/auth'

const mockedGetCurrentUser = vi.mocked(getCurrentUser)

describe('authStore initializeAuth', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isInitializing: false,
    })
    useRbacStore.getState().clearRbac()
    vi.clearAllMocks()
  })

  it('should skip when no token exists', async () => {
    await useAuthStore.getState().initializeAuth()
    expect(mockedGetCurrentUser).not.toHaveBeenCalled()
    expect(useAuthStore.getState().user).toBeNull()
  })

  it('should restore user from API when token exists', async () => {
    const user = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      role: 'engineer' as const,
      tenantId: '',
    }
    localStorage.setItem('kubeai_access_token', 'test-token')
    mockedGetCurrentUser.mockResolvedValueOnce({ success: true, data: user })

    await useAuthStore.getState().initializeAuth()

    const state = useAuthStore.getState()
    expect(state.user).toEqual(user)
    expect(state.isAuthenticated).toBe(true)
    expect(useRbacStore.getState().currentRole).toBe('engineer')
  })

  it('should not set user when API fails', async () => {
    localStorage.setItem('kubeai_access_token', 'test-token')
    mockedGetCurrentUser.mockResolvedValueOnce({ success: false, data: null })

    await useAuthStore.getState().initializeAuth()

    expect(useAuthStore.getState().user).toBeNull()
  })

  it('should handle API error gracefully', async () => {
    localStorage.setItem('kubeai_access_token', 'test-token')
    mockedGetCurrentUser.mockRejectedValueOnce(new Error('Network error'))

    await useAuthStore.getState().initializeAuth()

    expect(useAuthStore.getState().user).toBeNull()
    expect(useAuthStore.getState().isInitializing).toBe(false)
  })

  it('should set isInitializing during fetch', async () => {
    const user = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      role: 'admin' as const,
      tenantId: 't1',
    }
    localStorage.setItem('kubeai_access_token', 'test-token')

    let resolveApi: (v: unknown) => void
    const pending = new Promise((resolve) => {
      resolveApi = resolve
    })
    mockedGetCurrentUser.mockReturnValueOnce(pending as Promise<unknown>)

    const initPromise = useAuthStore.getState().initializeAuth()
    expect(useAuthStore.getState().isInitializing).toBe(true)

    resolveApi!({ success: true, data: user })
    await initPromise

    expect(useAuthStore.getState().isInitializing).toBe(false)
  })
})
