import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import DevEnvironmentsPage from '@/pages/dev-environments'

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

Element.prototype.scrollTo = vi.fn() as unknown as typeof Element.prototype.scrollTo

vi.mock('@/services/dev-environments', () => ({
  getDevEnvironments: vi.fn(),
  createDevEnvironment: vi.fn(),
  stopDevEnvironment: vi.fn(),
  startDevEnvironment: vi.fn(),
  deleteDevEnvironment: vi.fn(),
  getAccessUrl: vi.fn(),
}))

vi.mock('@/services/dev-environment-images', () => ({
  getSelectableDevEnvironmentImages: vi.fn(),
}))

vi.mock('@/services/datasets', () => ({
  getDatasets: vi.fn(),
  getDatasetDetail: vi.fn(),
}))

vi.mock('@/utils/messageHolder', () => ({
  getMessageInstance: vi.fn(() => ({
    success: vi.fn(),
    error: vi.fn(),
  })),
}))

vi.mock('@/stores/rbacStore', () => ({
  useRbacStore: vi.fn((selector: (state: { hasPermission: () => boolean }) => unknown) =>
    selector({ hasPermission: () => true }),
  ),
}))

const mockGetDevEnvironments = vi.mocked(
  await import('@/services/dev-environments'),
).getDevEnvironments
const mockGetSelectableDevEnvironmentImages = vi.mocked(
  await import('@/services/dev-environment-images'),
).getSelectableDevEnvironmentImages
const mockGetDatasets = vi.mocked(await import('@/services/datasets')).getDatasets

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <DevEnvironmentsPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

describe('DevEnvironmentsPage', () => {
  let consoleErrorSpy: ReturnType<typeof vi.spyOn>

  beforeEach(() => {
    vi.clearAllMocks()
    mockGetDevEnvironments.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })
    mockGetSelectableDevEnvironmentImages.mockResolvedValue([
      {
        id: 'image-jupyter',
        name: 'Jupyter 基础镜像',
        environmentType: 'jupyter',
        imageRef: 'harbor.local/kubeai/jupyter:latest',
        defaultCpu: '2',
        defaultMemory: '4Gi',
        defaultGpuCount: 0,
      },
    ])
    mockGetDatasets.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 100,
    })
    consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  afterEach(() => {
    consoleErrorSpy.mockRestore()
  })

  it('does not warn about circular references when selecting an environment type', async () => {
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout')

    renderPage()

    await waitFor(
      () => {
        expect(screen.getAllByRole('button', { name: /创建开发环境/ }).length).toBeGreaterThan(0)
      },
      { timeout: 10000 },
    )

    await userEvent.click(screen.getAllByRole('button', { name: /创建开发环境/ })[0])
    await userEvent.click(screen.getByLabelText('环境类型'))
    const scheduledCallsBeforeSelect = setTimeoutSpy.mock.calls.length
    await userEvent.click(await screen.findByText('Jupyter Notebook'))
    await new Promise((resolve) => setTimeout(resolve, 0))

    await waitFor(() => {
      const circularWarning = consoleErrorSpy.mock.calls.find((args) =>
        String(args[0]).includes('There may be circular references'),
      )
      expect(circularWarning).toBeUndefined()
    })

    const deferredImageReset = setTimeoutSpy.mock.calls
      .slice(scheduledCallsBeforeSelect)
      .find(
        ([handler, timeout]) =>
          timeout === undefined && String(handler).includes('environmentImageId'),
      )
    expect(deferredImageReset).toBeUndefined()

    setTimeoutSpy.mockRestore()
  }, 15000)
})
