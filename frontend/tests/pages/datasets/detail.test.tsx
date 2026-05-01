import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntApp, ConfigProvider } from 'antd'
import DatasetDetailPage from '@/pages/datasets/detail'
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
  getDatasetDetail: vi.fn(),
  deleteDataset: vi.fn(),
  createDatasetVersion: vi.fn(),
  deleteDatasetVersion: vi.fn(),
  uploadVersionFiles: vi.fn(),
}))

const mockGetDatasetDetail = vi.mocked(await import('@/services/datasets')).getDatasetDetail

const mockDataset = {
  id: 'ds-1',
  name: 'test-dataset',
  description: 'A test dataset',
  tenantId: 't-1',
  createdBy: 'u-1',
  createdByName: 'admin',
  versionCount: 2,
  totalFileCount: 10,
  totalSizeBytes: 2048,
  createdAt: '2026-04-30T12:00:00Z',
  updatedAt: '2026-04-30T12:00:00Z',
  versions: [
    {
      id: 'v-1',
      datasetId: 'ds-1',
      versionNumber: 1,
      description: 'First version',
      storagePath: 'datasets/ds-1/v1/',
      fileCount: 5,
      totalSizeBytes: 1024,
      createdBy: 'u-1',
      createdAt: '2026-04-30T12:00:00Z',
    },
    {
      id: 'v-2',
      datasetId: 'ds-1',
      versionNumber: 2,
      description: 'Second version',
      storagePath: 'datasets/ds-1/v2/',
      fileCount: 5,
      totalSizeBytes: 1024,
      createdBy: 'u-1',
      createdAt: '2026-04-30T13:00:00Z',
    },
  ],
}

function renderPage(datasetId = 'ds-1') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <ConfigProvider>
      <AntApp>
        <QueryClientProvider client={queryClient}>
          <MemoryRouter initialEntries={[`/datasets/${datasetId}`]}>
            <Routes>
              <Route path="/datasets/:id" element={<DatasetDetailPage />} />
            </Routes>
          </MemoryRouter>
        </QueryClientProvider>
      </AntApp>
    </ConfigProvider>,
  )
}

function waitForDataset() {
  return waitFor(() => {
    // h2 tag is the page title, distinct from breadcrumb/descriptions
    expect(screen.getByRole('heading', { level: 2 })).toBeTruthy()
  })
}

describe('DatasetDetailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useRbacStore.getState().setRole('admin')
  })

  it('should render dataset detail with overview', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce({
      success: true,
      data: mockDataset,
    })

    renderPage()

    await waitForDataset()

    expect(screen.getByText('A test dataset')).toBeTruthy()
    expect(screen.getByText('admin')).toBeTruthy()
  })

  it('should show statistics in overview tab', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce({
      success: true,
      data: mockDataset,
    })

    renderPage()

    await waitForDataset()

    expect(screen.getByText('版本数')).toBeTruthy()
    expect(screen.getByText('文件数')).toBeTruthy()
    expect(screen.getByText('总大小')).toBeTruthy()
  })

  it('should show not found when dataset does not exist', async () => {
    mockGetDatasetDetail.mockRejectedValueOnce(new Error('Not found'))

    renderPage()

    await waitFor(() => {
      expect(screen.getByText(/数据集不存在或已被删除/)).toBeTruthy()
    })
  })

  it('should show create version and delete buttons for admin', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce({
      success: true,
      data: mockDataset,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('创建新版本')).toBeTruthy()
      expect(screen.getByText('删除数据集')).toBeTruthy()
    })
  })

  it('should hide manage buttons for non-admin user', async () => {
    useRbacStore.getState().setRole('annotator')

    mockGetDatasetDetail.mockResolvedValueOnce({
      success: true,
      data: mockDataset,
    })

    renderPage()

    await waitForDataset()

    expect(screen.queryByText('创建新版本')).toBeNull()
    expect(screen.queryByText('删除数据集')).toBeNull()
  })

  it('should render breadcrumb with dataset link', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce({
      success: true,
      data: mockDataset,
    })

    renderPage()

    await waitForDataset()

    // Breadcrumb should have "数据集" link
    const links = screen.getAllByText('数据集')
    expect(links.length).toBeGreaterThanOrEqual(1)
  })

  it('should render tab labels', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce({
      success: true,
      data: mockDataset,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('概览')).toBeTruthy()
      expect(screen.getByText('版本列表')).toBeTruthy()
    })
  })

  it('should show version data after switching to versions tab', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce({
      success: true,
      data: mockDataset,
    })

    renderPage()

    await waitForDataset()

    // Click versions tab
    const versionsTab = screen.getByText('版本列表')
    await userEvent.click(versionsTab)

    await waitFor(() => {
      expect(screen.getByText('v1')).toBeTruthy()
      expect(screen.getByText('v2')).toBeTruthy()
    })
  })
})
