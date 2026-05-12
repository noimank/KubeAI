import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ConfigProvider } from 'antd'
import ResourceAwarePanel from '@/components/ResourceAwarePanel'

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

vi.mock('@/hooks/useResourceQuota', () => ({
  useResourceQuota: vi.fn(),
}))

const mockUseResourceQuota = vi.mocked(await import('@/hooks/useResourceQuota')).useResourceQuota

describe('ResourceAwarePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should show loading state', () => {
    mockUseResourceQuota.mockReturnValue({
      quota: null,
      isLoading: true,
      refetch: vi.fn(),
      formatMemoryMi: (mi: number) => `${mi} Mi`,
    } as ReturnType<typeof mockUseResourceQuota>)

    render(
      <ConfigProvider>
        <ResourceAwarePanel />
      </ConfigProvider>,
    )

    expect(screen.getByText('资源配额')).toBeTruthy()
  })

  it('should show no quota info when quota is null', () => {
    mockUseResourceQuota.mockReturnValue({
      quota: null,
      isLoading: false,
      refetch: vi.fn(),
      formatMemoryMi: (mi: number) => `${mi} Mi`,
    } as ReturnType<typeof mockUseResourceQuota>)

    render(
      <ConfigProvider>
        <ResourceAwarePanel />
      </ConfigProvider>,
    )

    expect(screen.getByText('暂无配额信息')).toBeTruthy()
  })

  it('should render resource quota with progress bars', () => {
    mockUseResourceQuota.mockReturnValue({
      quota: {
        gpu: { used: 3, total: 8, percent: 37.5, level: 'ok' as const },
        cpu: { used: 12, total: 64, percent: 18.75, level: 'ok' as const },
        memory: { used: 32768, total: 262144, percent: 12.5, level: 'ok' as const },
        storage: { used: 102400, total: 512000, percent: 20, level: 'ok' as const },
      },
      isLoading: false,
      refetch: vi.fn(),
      formatMemoryMi: (mi: number) => (mi >= 1024 ? `${(mi / 1024).toFixed(1)} Gi` : `${mi} Mi`),
    } as ReturnType<typeof mockUseResourceQuota>)

    render(
      <ConfigProvider>
        <ResourceAwarePanel />
      </ConfigProvider>,
    )

    expect(screen.getByText('资源配额')).toBeTruthy()
    expect(screen.getByText('GPU')).toBeTruthy()
    expect(screen.getByText('CPU')).toBeTruthy()
    expect(screen.getByText('内存')).toBeTruthy()
    expect(screen.getByText('存储')).toBeTruthy()
    expect(screen.getByText('资源充足，可以提交')).toBeTruthy()
  })

  it('should show warning tip when resource level is warning', () => {
    mockUseResourceQuota.mockReturnValue({
      quota: {
        gpu: { used: 6, total: 8, percent: 75, level: 'warning' as const },
        cpu: { used: 12, total: 64, percent: 18.75, level: 'ok' as const },
        memory: { used: 32768, total: 262144, percent: 12.5, level: 'ok' as const },
        storage: { used: 102400, total: 512000, percent: 20, level: 'ok' as const },
      },
      isLoading: false,
      refetch: vi.fn(),
      formatMemoryMi: (mi: number) => (mi >= 1024 ? `${(mi / 1024).toFixed(1)} Gi` : `${mi} Mi`),
    } as ReturnType<typeof mockUseResourceQuota>)

    render(
      <ConfigProvider>
        <ResourceAwarePanel />
      </ConfigProvider>,
    )

    expect(screen.getByText('资源偏紧，请注意配额')).toBeTruthy()
  })

  it('should show danger tip when resource level is danger', () => {
    mockUseResourceQuota.mockReturnValue({
      quota: {
        gpu: { used: 8, total: 8, percent: 100, level: 'danger' as const },
        cpu: { used: 12, total: 64, percent: 18.75, level: 'ok' as const },
        memory: { used: 32768, total: 262144, percent: 12.5, level: 'ok' as const },
        storage: { used: 102400, total: 512000, percent: 20, level: 'ok' as const },
      },
      isLoading: false,
      refetch: vi.fn(),
      formatMemoryMi: (mi: number) => (mi >= 1024 ? `${(mi / 1024).toFixed(1)} Gi` : `${mi} Mi`),
    } as ReturnType<typeof mockUseResourceQuota>)

    render(
      <ConfigProvider>
        <ResourceAwarePanel />
      </ConfigProvider>,
    )

    expect(screen.getByText('资源不足，请释放资源或联系管理员')).toBeTruthy()
  })
})
