import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import ProfilePage from '@/pages/profile'
import type { User } from '@/types/auth'

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

let mockUser: User | null = null

vi.mock('@/stores/authStore', () => ({
  useAuthStore: vi.fn(
    (selector: (state: { user: User | null; setUser: (u: User) => void }) => unknown) =>
      selector({ user: mockUser, setUser: vi.fn() }),
  ),
}))

vi.mock('@/services/profile', () => ({
  updateProfile: vi.fn(),
  uploadAvatar: vi.fn(),
  changePassword: vi.fn(),
}))

const localUser: User = {
  id: 'u-local',
  username: 'localuser',
  email: 'local@example.com',
  nickname: '本地用户',
  role: 'engineer',
  authProvider: 'local',
}

const oidcUser: User = {
  id: 'u-oidc',
  username: 'oidcuser',
  email: 'oidc@example.com',
  nickname: '第三方用户',
  role: 'engineer',
  authProvider: 'oidc',
}

function renderPage() {
  return render(
    <MemoryRouter>
      <ProfilePage />
    </MemoryRouter>,
  )
}

function getInput(label: string): HTMLInputElement {
  return screen.getByLabelText(label) as HTMLInputElement
}

describe('ProfilePage 按认证方式控制可编辑性', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUser = null
  })

  it('本地用户可编辑昵称/邮箱并显示保存按钮', () => {
    mockUser = localUser
    renderPage()

    expect(getInput('昵称').disabled).toBe(false)
    expect(getInput('邮箱').disabled).toBe(false)
    expect(screen.queryByRole('button', { name: '保存修改' })).not.toBeNull()
    expect(screen.queryByText(/由身份提供方统一管理/)).toBeNull()
  })

  it('本地用户可修改密码', async () => {
    mockUser = localUser
    renderPage()

    await userEvent.click(screen.getByRole('tab', { name: /安全设置/ }))

    expect(getInput('当前密码').disabled).toBe(false)
    expect(screen.queryByRole('button', { name: '修改密码' })).not.toBeNull()
  })

  it('本地用户头像显示上传入口', () => {
    mockUser = localUser
    renderPage()

    expect(screen.queryByRole('img', { name: 'camera' })).not.toBeNull()
  })

  it('第三方登录用户头像仅展示, 不出现上传入口', () => {
    mockUser = oidcUser
    renderPage()

    expect(screen.queryByRole('img', { name: 'camera' })).toBeNull()
  })

  it('第三方登录用户昵称/邮箱只读且无保存按钮', () => {
    mockUser = oidcUser
    renderPage()

    expect(getInput('昵称').disabled).toBe(true)
    expect(getInput('邮箱').disabled).toBe(true)
    expect(screen.queryByRole('button', { name: '保存修改' })).toBeNull()
    expect(screen.queryByText(/基本信息由身份提供方统一管理/)).not.toBeNull()
  })

  it('第三方登录用户不显示修改密码表单', async () => {
    mockUser = oidcUser
    renderPage()

    await userEvent.click(screen.getByRole('tab', { name: /安全设置/ }))

    expect(screen.queryByLabelText('当前密码')).toBeNull()
    expect(screen.queryByRole('button', { name: '修改密码' })).toBeNull()
    expect(screen.queryByText(/无法在此修改密码/)).not.toBeNull()
  })
})
