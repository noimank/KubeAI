import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import DatasetsPage from '@/pages/datasets'
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

vi.mock('@/services/datasets', () => ({
  getDatasets: vi.fn(),
  getDatasetDetail: vi.fn(),
  deleteDataset: vi.fn(),
}))

vi.mock('@/utils/messageHolder', () => ({
  getMessageInstance: vi.fn(() => ({
    success: vi.fn(),
    error: vi.fn(),
  })),
}))

const mockGetDatasets = vi.mocked(await import('@/services/datasets')).getDatasets

const mockDataset = {
  id: 'ds-1',
  name: 'test-dataset',
  description: 'test',
  tenantId: 't-1',
  createdBy: 'u-1',
  createdByName: 'admin',
  versionCount: 2,
  totalFileCount: 10,
  totalSizeBytes: 1024,
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
        <DatasetsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DatasetsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useRbacStore.getState().setRole('admin')
  })

  it('should render table with datasets', async () => {
    mockGetDatasets.mockResolvedValueOnce({
      items: [mockDataset],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('test-dataset')).toBeTruthy()
    })
  })

  it('should show empty state when no datasets', async () => {
    mockGetDatasets.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/还没有数据集/)).toBeTruthy()
    })
  })

  it('should call getDatasets with correct params', async () => {
    mockGetDatasets.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(mockGetDatasets).toHaveBeenCalledWith(
        expect.objectContaining({
          current: 1,
          pageSize: 20,
        }),
      )
    })
  })

  it('should search by keyword', async () => {
    mockGetDatasets.mockResolvedValue({
      items: [],
      total: 0,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    const searchInput = await screen.findByPlaceholderText('搜索数据集名称')
    await userEvent.type(searchInput, 'test{Enter}')

    await waitFor(() => {
      expect(mockGetDatasets).toHaveBeenCalledWith(expect.objectContaining({ keyword: 'test' }))
    })
  })
})
