import { describe, it, expect, beforeEach } from 'vitest'
import { useAuthStore } from '@/stores/authStore'

describe('authStore', () => {
  beforeEach(() => {
    localStorage.clear()
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
    })
  })

  it('should start with null state when no stored tokens', () => {
    const state = useAuthStore.getState()
    expect(state.user).toBeNull()
    expect(state.accessToken).toBeNull()
    expect(state.isAuthenticated).toBe(false)
  })

  it('should set user and tokens on login', () => {
    const user = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      role: 'admin',
      tenant_id: 'tenant-1',
    }
    useAuthStore.getState().login(user, 'access-token', 'refresh-token')

    const state = useAuthStore.getState()
    expect(state.user).toEqual(user)
    expect(state.accessToken).toBe('access-token')
    expect(state.refreshToken).toBe('refresh-token')
    expect(state.isAuthenticated).toBe(true)
    expect(localStorage.getItem('kubeai_access_token')).toBe('access-token')
  })

  it('should clear state on logout', () => {
    const user = {
      id: '1',
      username: 'testuser',
      email: 'test@example.com',
      role: 'admin',
      tenant_id: 'tenant-1',
    }
    useAuthStore.getState().login(user, 'access-token', 'refresh-token')
    useAuthStore.getState().logout()

    const state = useAuthStore.getState()
    expect(state.user).toBeNull()
    expect(state.accessToken).toBeNull()
    expect(state.isAuthenticated).toBe(false)
    expect(localStorage.getItem('kubeai_access_token')).toBeNull()
  })

  it('should update tokens', () => {
    useAuthStore.getState().setTokens('new-access', 'new-refresh')

    const state = useAuthStore.getState()
    expect(state.accessToken).toBe('new-access')
    expect(state.refreshToken).toBe('new-refresh')
  })
})
