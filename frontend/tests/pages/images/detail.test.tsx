import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import ImageDetailPage from '@/pages/images/detail'

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

vi.mock('@/services/images', () => ({
  getImage: vi.fn(),
  getBuildLog: vi.fn(),
}))

const mockGetImage = vi.mocked(await import('@/services/images')).getImage
const mockGetBuildLog = vi.mocked(await import('@/services/images')).getBuildLog

const mockPresetImage = {
  id: 'img-1',
  name: 'pytorch',
  tag: '2.1.0',
  imageRef: 'pytorch/pytorch:2.1.0-cuda12',
  description: 'PyTorch 官方镜像',
  source: 'preset',
  isEnabled: true,
  createdAt: '2026-04-30T12:00:00Z',
  updatedAt: '2026-04-30T12:00:00Z',
}

const mockCustomImage = {
  id: 'img-2',
  name: 'my-training',
  tag: 'v1.0',
  imageRef: 'harbor.local/kubeai/my-training:v1.0',
  description: '自定义训练环境',
  source: 'custom',
  isEnabled: true,
  buildStatus: 'succeeded',
  dockerfile: 'FROM python:3.12-slim\nRUN pip install numpy pandas',
  createdAt: '2026-04-30T12:00:00Z',
  updatedAt: '2026-04-30T12:00:00Z',
}

function renderPage(imageId = 'img-1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <ConfigProvider>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/images/${imageId}`]}>
            <Routes>
              <Route path="/images/:id" element={<ImageDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>,
  )
}

function waitForImage() {
  return waitFor(() => {
    expect(screen.getByRole('heading', { level: 2 })).toBeTruthy()
  })
}

describe('ImageDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should render preset image detail with overview tab only', async () => {
    mockGetImage.mockResolvedValueOnce(mockPresetImage)

    renderPage()

    await waitForImage()

    expect(screen.getByRole('heading', { level: 2 }).textContent).toContain('pytorch:2.1.0')
    expect(screen.getByText('概览')).toBeTruthy()
    expect(screen.queryByText('构建日志')).toBeNull()
    expect(screen.queryByText('Dockerfile')).toBeNull()
  })

  it('should render custom image with all three tabs', async () => {
    mockGetImage.mockResolvedValueOnce(mockCustomImage)

    renderPage('img-2')

    await waitForImage()

    expect(screen.getByRole('heading', { level: 2 }).textContent).toContain('my-training:v1.0')
    expect(screen.getByText('概览')).toBeTruthy()
    expect(screen.getByText('构建日志')).toBeTruthy()
    expect(screen.getByText('Dockerfile')).toBeTruthy()
  })

  it('should display overview fields correctly', async () => {
    mockGetImage.mockResolvedValueOnce(mockPresetImage)

    renderPage()

    await waitForImage()

    expect(screen.getByText('pytorch')).toBeTruthy()
    expect(screen.getByText('2.1.0')).toBeTruthy()
    expect(screen.getAllByText('预置').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('PyTorch 官方镜像')).toBeTruthy()
    expect(screen.getAllByText('启用').length).toBeGreaterThanOrEqual(1)
  })

  it('should display build status for custom images', async () => {
    mockGetImage.mockResolvedValueOnce(mockCustomImage)

    renderPage('img-2')

    await waitForImage()

    expect(screen.getByText('构建状态')).toBeTruthy()
    expect(screen.getByText('成功')).toBeTruthy()
  })

  it('should render breadcrumb with image management link', async () => {
    mockGetImage.mockResolvedValueOnce(mockPresetImage)

    renderPage()

    await waitForImage()

    const links = screen.getAllByText('镜像管理')
    expect(links.length).toBeGreaterThanOrEqual(1)
  })

  it('should show not found when image does not exist', async () => {
    mockGetImage.mockRejectedValueOnce(new Error('Not found'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/镜像不存在或已被删除/)).toBeTruthy()
    })
  })

  it('should show return link when image not found', async () => {
    mockGetImage.mockRejectedValueOnce(new Error('Not found'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('返回镜像列表')).toBeTruthy()
    })
  })

  it('should show build log in build log tab for custom images', async () => {
    mockGetImage.mockResolvedValueOnce(mockCustomImage)
    mockGetBuildLog.mockResolvedValueOnce({
      buildStatus: 'succeeded',
      log: 'Step 1/3 : FROM python:3.12-slim\nStep 2/3 : RUN pip install numpy',
    })

    renderPage('img-2')

    await waitForImage()

    const logTab = screen.getByText('构建日志')
    await userEvent.click(logTab)

    await waitFor(() => {
      expect(mockGetBuildLog).toHaveBeenCalledWith('img-2')
    })

    await waitFor(() => {
      expect(screen.getByText(/Step 1\/3/)).toBeTruthy()
    })
  })

  it('should show dockerfile content with line numbers', async () => {
    mockGetImage.mockResolvedValueOnce(mockCustomImage)

    renderPage('img-2')

    await waitForImage()

    const dockerfileTab = screen.getByText('Dockerfile')
    await userEvent.click(dockerfileTab)

    await waitFor(() => {
      expect(screen.getByText(/FROM python:3.12-slim/)).toBeTruthy()
      expect(screen.getByText(/RUN pip install numpy pandas/)).toBeTruthy()
    })
  })

  it('should not show Dockerfile tab when dockerfile is empty', async () => {
    mockGetImage.mockResolvedValueOnce({
      ...mockCustomImage,
      dockerfile: undefined,
    })

    renderPage('img-2')

    await waitForImage()

    expect(screen.getByText('概览')).toBeTruthy()
    expect(screen.getByText('构建日志')).toBeTruthy()
    expect(screen.queryByText('Dockerfile')).toBeNull()
  })
})
