import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import ExperimentsPage from '@/pages/experiments/index'

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

vi.mock('@/services/experiments', () => ({
  getExperiments: vi.fn(),
}))

vi.mock('@/services/datasets', () => ({
  getDatasets: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 100 }),
}))

vi.mock('@/services/images', () => ({
  getImages: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 100 }),
}))

vi.mock('@/stores/rbacStore', () => ({
  useRbacStore: vi.fn((selector) => {
    const state = { hasPermission: (perm: string) => perm === 'experiments:read' }
    return selector(state)
  }),
}))

vi.mock('@/stores/tenantStore', () => ({
  useTenantStore: vi.fn((selector) => {
    const state = { currentTenant: null, tenantList: [], loading: false }
    return selector(state)
  }),
}))

const mockGetExperiments = vi.mocked(await import('@/services/experiments')).getExperiments

const mockExperiment = {
  id: 'exp-1',
  tenantId: 't-1',
  trainingJobId: 'job-1',
  trainingJobName: 'test-training',
  mlflowExperimentId: '42',
  mlflowRunId: 'run-abc',
  status: 'active' as const,
  hyperparameters: { lr: '0.001', epochs: '10', batch_size: '32' },
  metrics: [{ key: 'loss', value: 0.5 }],
  datasetVersion: 'v1',
  imageName: 'PyTorch 2.1',
  createdAt: '2026-05-11T10:00:00Z',
  updatedAt: '2026-05-11T10:00:00Z',
}

const mockCompletedExperiment = {
  ...mockExperiment,
  id: 'exp-2',
  trainingJobName: 'completed-training',
  status: 'completed' as const,
  metrics: [{ key: 'accuracy', value: 0.95 }],
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <ConfigProvider>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter>
            <ExperimentsPage />
          </MemoryRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>,
  )
}

describe('ExperimentsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render table with experiments', async () => {
    mockGetExperiments.mockResolvedValueOnce({
      items: [mockExperiment, mockCompletedExperiment],
      total: 2,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      // "test-training" appears in both the training job column and experiment name column
      const elements = screen.getAllByText('test-training')
      expect(elements.length).toBeGreaterThanOrEqual(1)
    })

    // "completed-training" also appears in both training job and experiment name columns
    expect(screen.getAllByText('completed-training').length).toBeGreaterThanOrEqual(1)
  })

  it('should show empty state when no experiments', async () => {
    mockGetExperiments.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('还没有实验记录，提交训练任务后实验会自动追踪到这里')).toBeTruthy()
    })
  })

  it('should render status filter tabs', async () => {
    mockGetExperiments.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('全部')).toBeTruthy()
    })
  })

  it('should render search input', async () => {
    mockGetExperiments.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByPlaceholderText('搜索训练任务名称')).toBeTruthy()
    })
  })

  it('should display hyperparameters and metrics', async () => {
    mockGetExperiments.mockResolvedValueOnce({
      items: [mockExperiment],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/lr=0.001/)).toBeTruthy()
    })
    expect(screen.getByText(/loss: 0.5000/)).toBeTruthy()
  })

  it('should display dataset version and image name', async () => {
    mockGetExperiments.mockResolvedValueOnce({
      items: [mockExperiment],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('v1')).toBeTruthy()
      expect(screen.getByText('PyTorch 2.1')).toBeTruthy()
    })
  })

  it('should handle search input change', async () => {
    const user = userEvent.setup()
    mockGetExperiments.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByPlaceholderText('搜索训练任务名称')).toBeTruthy()
    })

    const searchInput = screen.getByPlaceholderText('搜索训练任务名称')
    await user.type(searchInput, 'my-experiment')
    expect((searchInput as HTMLInputElement).value).toBe('my-experiment')
  })
})
