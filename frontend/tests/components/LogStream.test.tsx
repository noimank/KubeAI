import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import LogStream from '@/components/LogStream'

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

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

describe('LogStream', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders empty state with custom text', () => {
    render(<LogStream emptyText="暂无日志" />)
    expect(screen.getByText('暂无日志')).toBeDefined()
  })

  it('renders initial lines', () => {
    render(<LogStream initialLines={['line 1', 'line 2', 'line 3']} />)
    expect(screen.getByText('line 1')).toBeDefined()
    expect(screen.getByText('line 2')).toBeDefined()
    expect(screen.getByText('line 3')).toBeDefined()
  })

  it('shows loading spinner', () => {
    const { container } = render(<LogStream loading />)
    expect(container.querySelector('.ant-spin')).toBeDefined()
  })

  it('displays line count', () => {
    render(<LogStream initialLines={['a', 'b', 'c']} />)
    expect(screen.getByText('3 行')).toBeDefined()
  })

  it('renders search input', () => {
    render(<LogStream />)
    expect(screen.getByPlaceholderText('搜索日志...')).toBeDefined()
  })

  it('detects error lines', () => {
    const { container } = render(
      <LogStream
        initialLines={['normal line', 'ERROR: something failed', 'Traceback (most recent call)']}
      />,
    )
    const lines = Array.from(container.querySelectorAll('[style*="position: absolute"]'))
    const errorLine = lines.find((el) => el.textContent?.includes('ERROR'))
    expect(errorLine).toBeDefined()
    expect(errorLine?.getAttribute('style')).toContain('255, 77, 79, 0.1')
  })
})
