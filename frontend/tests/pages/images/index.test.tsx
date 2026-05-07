import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ImagesPage from '@/pages/images'
import { useRbacStore } from '@/stores/rbacStore'

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
  getImages: vi.fn(),
  createImage: vi.fn(),
  updateImage: vi.fn(),
  deleteImage: vi.fn(),
  toggleImage: vi.fn(),
  buildImage: vi.fn(),
  getBuildLog: vi.fn(),
  rebuildImage: vi.fn(),
}))

vi.mock('@/utils/messageHolder', () => ({
  getMessageInstance: vi.fn(() => ({
    success: vi.fn(),
    error: vi.fn(),
  })),
}))

const mockGetImages = vi.mocked(await import('@/services/images')).getImages

const mockPresetImage = {
  id: 'img-1',
  name: 'pytorch',
  tag: '2.1.0',
  imageRef: 'pytorch/pytorch:2.1.0-cuda12',
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
  source: 'custom',
  isEnabled: true,
  buildStatus: 'succeeded' as const,
  createdAt: '2026-04-30T12:00:00Z',
  updatedAt: '2026-04-30T12:00:00Z',
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ImagesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ImagesPage enhancements', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useRbacStore.getState().setRole('admin')
  })

  it('should render name as clickable link', async () => {
    mockGetImages.mockResolvedValueOnce({
      items: [mockPresetImage],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('pytorch')).toBeTruthy()
    })

    const link = screen.getByRole('link', { name: 'pytorch' })
    expect(link).toBeTruthy()
    expect(link.getAttribute('href')).toBe('/images/img-1')
  })

  it('should show custom-specific empty text when custom tab is selected', async () => {
    mockGetImages.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    // Click custom tab
    const customTab = screen.getByText('自定义')
    await userEvent.click(customTab)

    await waitFor(() => {
      expect(screen.getByText(/还没有自定义镜像/)).toBeTruthy()
    })
  })

  it('should show preset-specific empty text when preset tab is selected', async () => {
    mockGetImages.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    const presetTab = screen.getByText('预置')
    await userEvent.click(presetTab)

    await waitFor(() => {
      expect(screen.getByText(/还没有预置镜像/)).toBeTruthy()
    })
  })

  it('should show default empty text when all tab is selected', async () => {
    mockGetImages.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/还没有镜像，添加第一个镜像开始吧/)).toBeTruthy()
    })
  })

  it('should show view detail link for custom images', async () => {
    mockGetImages.mockResolvedValueOnce({
      items: [mockCustomImage],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('my-training')).toBeTruthy()
    })

    const detailLink = screen.getByRole('link', { name: '查看详情' })
    expect(detailLink).toBeTruthy()
    expect(detailLink.getAttribute('href')).toBe('/images/img-2')
  })

  it('should not show view detail link for preset images', async () => {
    mockGetImages.mockResolvedValueOnce({
      items: [mockPresetImage],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('pytorch')).toBeTruthy()
    })

    expect(screen.queryByText('查看详情')).toBeNull()
  })
})
