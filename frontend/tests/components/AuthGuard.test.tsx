import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import AuthGuard from '@/components/AuthGuard'
import { useAuthStore } from '@/stores/authStore'

describe('AuthGuard', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isInitializing: false,
    })
  })

  it('should redirect to login when not authenticated', () => {
    render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthGuard />
      </MemoryRouter>,
    )

    expect(screen.queryByText(/./)).toBeNull()
  })

  it('should render outlet when authenticated', () => {
    useAuthStore.setState({ isAuthenticated: true })
    const { container } = render(
      <MemoryRouter initialEntries={['/dashboard']}>
        <AuthGuard />
      </MemoryRouter>,
    )

    expect(container.querySelector('.ant-spin')).toBeNull()
  })

  it('should show spinner when initializing', () => {
    useAuthStore.setState({ isInitializing: true })
    render(
      <MemoryRouter>
        <AuthGuard />
      </MemoryRouter>,
    )

    const spinner = document.querySelector('.ant-spin-spinning')
    expect(spinner).toBeTruthy()
  })
})
