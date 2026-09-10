import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import CreateTrainingJobPage from '@/pages/training-jobs/create'
import type { DevEnvironment } from '@/types/dev-environment'

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

vi.mock('@/services/datasets', () => ({
  getDatasets: vi.fn(),
  getDatasetDetail: vi.fn(),
}))

vi.mock('@/services/images', () => ({
  getSelectableImages: vi.fn(),
}))

vi.mock('@/services/dev-environments', () => ({
  getDevEnvironment: vi.fn(),
}))

vi.mock('@/services/experiments', () => ({
  getExperiment: vi.fn(),
}))

vi.mock('@/services/business-configs', () => ({
  getBusinessConfigs: vi.fn(),
}))

vi.mock('@/services/training-jobs', () => ({
  createTrainingJob: vi.fn(),
  createTrainingJobFromEnvironment: vi.fn(),
}))

vi.mock('@/components/ResourceAwarePanel', () => ({
  default: () => <div data-testid="resource-panel" />,
}))

vi.mock('@/utils/messageHolder', () => ({
  getMessageInstance: vi.fn(() => ({
    success: vi.fn(),
    error: vi.fn(),
  })),
}))

const services = await import('@/services/training-jobs')
const mockCreateTrainingJob = vi.mocked(services.createTrainingJob)
const mockCreateFromEnvironment = vi.mocked(services.createTrainingJobFromEnvironment)
const mockGetDevEnvironment = vi.mocked(
  await import('@/services/dev-environments'),
).getDevEnvironment
const mockGetDatasets = vi.mocked(await import('@/services/datasets')).getDatasets
const mockGetDatasetDetail = vi.mocked(await import('@/services/datasets')).getDatasetDetail
const mockGetSelectableImages = vi.mocked(await import('@/services/images')).getSelectableImages
const mockGetBusinessConfigs = vi.mocked(
  await import('@/services/business-configs'),
).getBusinessConfigs

function makeEnv(overrides: Partial<DevEnvironment> = {}): DevEnvironment {
  return {
    id: 'env-1',
    tenantId: 'tenant-1',
    createdBy: 'user-1',
    name: 'pytorch-dev',
    image: 'harbor.local/kubeai/jupyter:latest',
    gpuCount: 2,
    cpu: '8',
    memory: '16Gi',
    status: 'running',
    envVars: { HF_ENDPOINT: 'https://hf-mirror.com' },
    mountedDatasets: [
      {
        datasetId: 'ds-1',
        datasetName: 'MNIST',
        versionId: 'ver-1',
        versionNumber: '3',
        mountPath: '/kubeai/datasets/MNIST',
      },
    ],
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

function renderPage(search = '') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <MemoryRouter initialEntries={[`/training-jobs/create${search}`]}>
      <QueryClientProvider client={queryClient}>
        <CreateTrainingJobPage />
      </QueryClientProvider>
    </MemoryRouter>,
  )
}

async function fillAndWalkToSubmit() {
  const nameInput = screen.getByLabelText('任务名称')
  await userEvent.clear(nameInput)
  await userEvent.type(nameInput, 'pytorch-dev-train')
  await userEvent.type(screen.getByLabelText('启动命令'), 'python3 train.py')

  await userEvent.click(screen.getByRole('button', { name: '下一步' }))
  await waitFor(() => expect(screen.getByText('启用 GPU')).toBeTruthy())
  await userEvent.click(screen.getByRole('button', { name: '下一步' }))
  await waitFor(() => expect(screen.getByRole('button', { name: '提交任务' })).toBeTruthy())
}

describe('CreateTrainingJobPage from_environment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetDatasets.mockResolvedValue({
      items: [{ id: 'ds-1', name: 'MNIST' }],
      total: 1,
      page: 1,
      pageSize: 100,
    })
    mockGetDatasetDetail.mockResolvedValue({
      id: 'ds-1',
      name: 'MNIST',
      versions: [{ id: 'ver-1', versionNumber: 3 }],
    } as never)
    mockCreateTrainingJob.mockResolvedValue({ id: 'job-1' } as never)
    mockCreateFromEnvironment.mockResolvedValue({ id: 'job-1' } as never)
    mockGetSelectableImages.mockResolvedValue([])
    mockGetBusinessConfigs.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 100,
    })
  })

  it('按开发环境预填表单并提示来源', async () => {
    mockGetDevEnvironment.mockResolvedValue(makeEnv())
    renderPage('?from_environment=env-1')

    await screen.findByText(/正在从开发环境「pytorch-dev」发起训练/)
    await waitFor(() =>
      expect((screen.getByLabelText('任务名称') as HTMLInputElement).value).toBe(
        'pytorch-dev-train',
      ),
    )
    expect((screen.getByLabelText('描述') as HTMLTextAreaElement).value).toBe(
      '来自开发环境「pytorch-dev」',
    )
    expect(
      screen.getByText('留空则使用环境当前镜像 harbor.local/kubeai/jupyter:latest'),
    ).toBeTruthy()
  })

  it('提交时走 from-environment 端点并携带环境 ID', async () => {
    mockGetDevEnvironment.mockResolvedValue(makeEnv())
    renderPage('?from_environment=env-1')

    await waitFor(() =>
      expect((screen.getByLabelText('任务名称') as HTMLInputElement).value).toBe(
        'pytorch-dev-train',
      ),
    )
    await fillAndWalkToSubmit()
    await userEvent.click(screen.getByRole('button', { name: '提交任务' }))

    await waitFor(() => expect(mockCreateFromEnvironment).toHaveBeenCalledTimes(1))
    expect(mockCreateFromEnvironment).toHaveBeenCalledWith(
      expect.objectContaining({
        environmentId: 'env-1',
        name: 'pytorch-dev-train',
        command: 'python3 train.py',
        imageId: undefined,
        gpuCount: 2,
        cpu: '8',
        memory: '16Gi',
        envVars: { HF_ENDPOINT: 'https://hf-mirror.com' },
        datasetId: 'ds-1',
        datasetVersionId: 'ver-1',
      }),
    )
    expect(mockCreateTrainingJob).not.toHaveBeenCalled()
  }, 30000)

  it('环境未运行时显示警告并禁用提交', async () => {
    mockGetDevEnvironment.mockResolvedValue(makeEnv({ status: 'stopped' }))
    renderPage('?from_environment=env-1')

    await screen.findByText(/当前未在运行中/)
    await fillAndWalkToSubmit()
    const submitBtn = screen.getByRole('button', { name: '提交任务' }) as HTMLButtonElement
    expect(submitBtn.disabled).toBe(true)
    expect(mockCreateFromEnvironment).not.toHaveBeenCalled()
  }, 30000)
})
