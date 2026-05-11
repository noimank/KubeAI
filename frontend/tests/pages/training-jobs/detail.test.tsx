import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import TrainingJobDetailPage from '@/pages/training-jobs/detail'

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
  getTrainingJob: vi.fn(),
  getTrainingJobPods: vi.fn(),
  getTrainingJobLogs: vi.fn(),
  getTrainingJobMetrics: vi.fn(),
  stopTrainingJob: vi.fn(),
  retryTrainingJob: vi.fn(),
  buildLogStreamUrl: vi.fn(),
}))

vi.mock('@/stores/rbacStore', () => ({
  useRbacStore: vi.fn((selector) => {
    const state = { hasPermission: (perm: string) => perm === 'training_jobs:write' }
    return selector(state)
  }),
}))

const mockGetTrainingJob = vi.mocked(await import('@/services/training-jobs')).getTrainingJob
const mockRetryTrainingJob = vi.mocked(await import('@/services/training-jobs')).retryTrainingJob

vi.mocked(await import('@/services/training-jobs')).getTrainingJobPods.mockResolvedValue([])
vi.mocked(await import('@/services/training-jobs')).buildLogStreamUrl.mockReturnValue('')

const mockRunningJob = {
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
  vcjobName: 'training-test-training',
  createdAt: '2026-05-11T10:00:00Z',
  updatedAt: '2026-05-11T10:00:00Z',
}

const mockFailedJob = {
  ...mockRunningJob,
  id: 'job-2',
  status: 'failed',
  errorMessage: '内存不足 (OOM)：训练容器因超出内存限制被终止。',
  startedAt: '2026-05-11T10:00:00Z',
  finishedAt: '2026-05-11T11:00:00Z',
}

const mockSucceededJob = {
  ...mockRunningJob,
  id: 'job-3',
  status: 'succeeded',
  startedAt: '2026-05-11T10:00:00Z',
  finishedAt: '2026-05-11T11:00:00Z',
}

const mockStoppedJob = {
  ...mockRunningJob,
  id: 'job-4',
  status: 'stopped',
  startedAt: '2026-05-11T10:00:00Z',
  finishedAt: '2026-05-11T11:00:00Z',
}

function renderPage(jobId = 'job-1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <ConfigProvider>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/training-jobs/${jobId}`]}>
            <Routes>
              <Route path="/training-jobs/:id" element={<TrainingJobDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>,
  )
}

function waitForJob() {
  return waitFor(() => {
    expect(screen.getByRole('heading', { level: 2 })).toBeTruthy()
  })
}

describe('TrainingJobDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render running job with stop button', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockRunningJob)

    renderPage()

    await waitForJob()

    expect(screen.getByText('停止任务')).toBeTruthy()
  })

  it('should not show stop button for succeeded job', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockSucceededJob)

    renderPage('job-3')

    await waitForJob()

    expect(screen.queryByText('停止任务')).toBeNull()
  })

  it('should show error alert for failed job', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockFailedJob)

    renderPage('job-2')

    await waitForJob()

    expect(screen.getByText('失败原因')).toBeTruthy()
    expect(screen.getByText(/OOM/)).toBeTruthy()
  })

  it('should show retry button for failed job', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockFailedJob)

    renderPage('job-2')

    await waitForJob()

    expect(screen.getByText('重新训练')).toBeTruthy()
  })

  it('should show retry button for stopped job', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockStoppedJob)

    renderPage('job-4')

    await waitForJob()

    expect(screen.getByText('重新训练')).toBeTruthy()
  })

  it('should not show retry button for succeeded job', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockSucceededJob)

    renderPage('job-3')

    await waitForJob()

    expect(screen.queryByText('重新训练')).toBeNull()
  })

  it('should render stop button with popconfirm wrapper', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockRunningJob)

    renderPage()

    await waitForJob()

    expect(screen.getByText('停止任务')).toBeTruthy()
    // Verify popconfirm is present by checking aria-describedby on parent
    const stopBtn = screen.getByText('停止任务').closest('button')
    expect(
      stopBtn?.classList.contains('ant-popover-open') || stopBtn?.getAttribute('aria-describedby'),
    ).toBeTruthy()
  })

  it('should trigger retry mutation on retry click', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockFailedJob)
    mockRetryTrainingJob.mockResolvedValueOnce({
      ...mockFailedJob,
      id: 'job-new',
      name: 'test-training-retry-202605111000',
      status: 'queued',
    })

    renderPage('job-2')

    await waitForJob()

    const retryBtn = screen.getByText('重新训练')
    await userEvent.click(retryBtn)

    await waitFor(() => {
      expect(mockRetryTrainingJob).toHaveBeenCalledWith('job-2', expect.anything())
    })
  })

  it('should show view logs link in failure alert', async () => {
    mockGetTrainingJob.mockResolvedValueOnce(mockFailedJob)

    renderPage('job-2')

    await waitForJob()

    expect(screen.getByText('查看日志 →')).toBeTruthy()
  })
})
