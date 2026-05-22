import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import LoginPage from '@/pages/login'
import { useAuthStore } from '@/stores/authStore'

vi.mock('@/services/auth', () => ({
  getAuthConfig: vi.fn().mockResolvedValue({ data: { allowUserRegistration: false } }),
  getCurrentUser: vi.fn(),
  login: vi.fn(),
}))

vi.mock('@/utils/messageHolder', () => ({
  getMessageInstance: vi.fn(() => ({
    error: vi.fn(),
  })),
}))

describe('LoginPage', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })

    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isInitializing: false,
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('does not emit the deprecated Ant Design Card bordered warning', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined)

    render(
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(
        consoleError.mock.calls.some((call) =>
          call.some(
            (message) =>
              typeof message === 'string' &&
              message.includes('[antd: Card]') &&
              message.includes('`bordered` is deprecated'),
          ),
        ),
      ).toBe(false)
    })
  })
})
