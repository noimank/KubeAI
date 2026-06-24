import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
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

// jsdom does not implement these; stub them so effects/interactions don't throw.
Element.prototype.scrollIntoView = vi.fn()
HTMLAnchorElement.prototype.click = vi.fn()

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

  // Regression: the old virtual scroller rendered only the first BUFFER (10)
  // lines whenever containerHeight hadn't been measured yet.
  it('renders all lines beyond the previous virtual-scroll buffer', () => {
    const lines = Array.from({ length: 50 }, (_, i) => `line-${i}`)
    render(<LogStream initialLines={lines} />)
    expect(screen.getByText('line-0')).toBeDefined()
    expect(screen.getByText('line-49')).toBeDefined()
    expect(screen.getByText('50 行')).toBeDefined()
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
    const errorLine = Array.from(container.querySelectorAll('[data-idx]')).find((el) =>
      el.textContent?.includes('ERROR'),
    )
    expect(errorLine).toBeDefined()
    expect(errorLine?.getAttribute('style')).toContain('255, 77, 79, 0.1')
  })

  it('shows match count while searching', async () => {
    const user = userEvent.setup()
    render(<LogStream initialLines={['foo', 'bar', 'foo again']} />)
    await user.type(screen.getByPlaceholderText('搜索日志...'), 'foo')
    expect(screen.getByText('1/2')).toBeDefined()
  })

  it('downloads current log via blob', async () => {
    const user = userEvent.setup()
    const createObjectURL = vi.fn(() => 'blob:fake')
    const revokeObjectURL = vi.fn()
    Object.defineProperty(URL, 'createObjectURL', {
      value: createObjectURL,
      configurable: true,
      writable: true,
    })
    Object.defineProperty(URL, 'revokeObjectURL', {
      value: revokeObjectURL,
      configurable: true,
      writable: true,
    })

    render(<LogStream initialLines={['foo', 'bar']} downloadName="job-x" />)
    await user.click(screen.getByRole('button', { name: /下载/ }))

    expect(createObjectURL).toHaveBeenCalledTimes(1)
    expect(revokeObjectURL).toHaveBeenCalledTimes(1)
  })

  it('disables download when there are no lines', () => {
    render(<LogStream />)
    const btn = screen.getByRole('button', { name: /下载/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
  })

  it('splits a k8s timestamp prefix from log content', () => {
    render(
      <LogStream initialLines={['2024-01-15T10:30:45.123Z starting training', 'plain line']} />,
    )
    // Content is rendered without the raw RFC3339 prefix...
    expect(screen.getByText('starting training')).toBeDefined()
    expect(screen.getByText('plain line')).toBeDefined()
    // ...the prefix is shown as a formatted HH:MM:SS timestamp instead.
    expect(screen.getByText(/\d{2}:\d{2}:\d{2}/)).toBeDefined()
    expect(screen.queryByText(/2024-01-15T10:30:45/)).toBeNull()
  })
})
