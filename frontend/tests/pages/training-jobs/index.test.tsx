import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import TrainingJobsPage from '@/pages/training-jobs/index'

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

vi.mock('@/services/training-jobs', () => ({
  getTrainingJobs: vi.fn(),
  getTrainingJob: vi.fn(),
  stopTrainingJob: vi.fn(),
}))

vi.mock('@/utils/messageHolder', () => ({
  getMessageInstance: vi.fn(() => ({
    success: vi.fn(),
    error: vi.fn(),
  })),
}))

vi.mock('@/stores/rbacStore', () => ({
  useRbacStore: vi.fn((selector) => {
    const state = { hasPermission: (perm: string) => perm === 'training_jobs:write' }
    return selector(state)
  }),
}))

vi.mock('@/hooks/useWebSocket', () => ({
  useWebSocket: vi.fn(),
}))

vi.mock('@/stores/tenantStore', () => ({
  useTenantStore: vi.fn((selector) => {
    const state = { currentTenant: null, tenantList: [], loading: false }
    return selector(state)
  }),
}))

const mockGetTrainingJobs = vi.mocked(await import('@/services/training-jobs')).getTrainingJobs

const mockJob = {
  id: 'job-1',
  tenantId: 't-1',
  name: 'test-training',
  status: 'running',
  command: 'python train.py',
  gpuCount: 2,
  gpuMode: 'exclusive',
  cpu: '4',
  memory: '8Gi',
  priority: 'normal',
  workerCount: 1,
  vcjobName: 'training-test',
  createdAt: '2026-05-11T10:00:00Z',
  updatedAt: '2026-05-11T10:00:00Z',
}

const mockQueuedJob = {
  ...mockJob,
  id: 'job-2',
  name: 'queued-job',
  status: 'queued',
}

const mockSucceededJob = {
  ...mockJob,
  id: 'job-3',
  name: 'succeeded-job',
  status: 'succeeded',
  startedAt: '2026-05-11T10:00:00Z',
  finishedAt: '2026-05-11T11:00:00Z',
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
            <TrainingJobsPage />
          </MemoryRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>,
  )
}

describe('TrainingJobsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render table with training jobs', async () => {
    mockGetTrainingJobs.mockResolvedValueOnce({
      items: [mockJob, mockQueuedJob, mockSucceededJob],
      total: 3,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('test-training')).toBeTruthy()
      expect(screen.getByText('queued-job')).toBeTruthy()
      expect(screen.getByText('succeeded-job')).toBeTruthy()
    })
  })

  it('should show empty state when no jobs', async () => {
    mockGetTrainingJobs.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/还没有训练任务/)).toBeTruthy()
    })
  })

  it('should show create button in empty state', async () => {
    mockGetTrainingJobs.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('新建任务')).toBeTruthy()
    })
  })

  it('should render status tags with correct colors', async () => {
    mockGetTrainingJobs.mockResolvedValueOnce({
      items: [mockJob],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('运行中')).toBeTruthy()
    })
  })

  it('should display GPU count column', async () => {
    mockGetTrainingJobs.mockResolvedValueOnce({
      items: [mockJob],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('2 张')).toBeTruthy()
    })
  })

  it('should have status filter segmented control', async () => {
    mockGetTrainingJobs.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('全部')).toBeTruthy()
      expect(screen.getByText('运行中')).toBeTruthy()
      expect(screen.getByText('已完成')).toBeTruthy()
    })
  })

  it('should filter by status when segmented changed', async () => {
    mockGetTrainingJobs.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(mockGetTrainingJobs).toHaveBeenCalled()
    })

    const runningTab = screen.getByText('运行中')
    await userEvent.click(runningTab)

    await waitFor(() => {
      expect(mockGetTrainingJobs).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'running' }),
      )
    })
  })

  it('should search by name', async () => {
    mockGetTrainingJobs.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    const searchInput = await screen.findByPlaceholderText('搜索任务名称')
    await userEvent.type(searchInput, 'test{Enter}')

    await waitFor(() => {
      expect(mockGetTrainingJobs).toHaveBeenCalledWith(expect.objectContaining({ name: 'test' }))
    })
  })
})
