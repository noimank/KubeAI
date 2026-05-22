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
  getVersionFiles: vi.fn(),
  getVersionStats: vi.fn(),
  getFileDownloadUrl: vi.fn(),
  mountDatasetVersion: vi.fn(),
  getDatasetMountInfo: vi.fn(),
  unmountDatasetVersion: vi.fn(),
}))

const mockGetDatasetDetail = vi.mocked(await import('@/services/datasets')).getDatasetDetail
const mockGetVersionFiles = vi.mocked(await import('@/services/datasets')).getVersionFiles
const mockGetVersionStats = vi.mocked(await import('@/services/datasets')).getVersionStats
const mockGetFileDownloadUrl = vi.mocked(await import('@/services/datasets')).getFileDownloadUrl

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
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)

    renderPage()

    await waitForDataset()

    expect(screen.getByText('A test dataset')).toBeTruthy()
    expect(screen.getByText('admin')).toBeTruthy()
  })

  it('should show statistics in overview tab', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)

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
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('创建新版本')).toBeTruthy()
      expect(screen.getByText('删除数据集')).toBeTruthy()
    })
  })

  it('should hide manage buttons for non-admin user', async () => {
    useRbacStore.getState().setRole('annotator')

    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)

    renderPage()

    await waitForDataset()

    expect(screen.queryByText('创建新版本')).toBeNull()
    expect(screen.queryByText('删除数据集')).toBeNull()
  })

  it('should render breadcrumb with dataset link', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)

    renderPage()

    await waitForDataset()

    // Breadcrumb should have "数据集" link
    const links = screen.getAllByText('数据集')
    expect(links.length).toBeGreaterThanOrEqual(1)
  })

  it('should render tab labels', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('概览')).toBeTruthy()
      expect(screen.getByText('版本列表')).toBeTruthy()
    })
  })

  it('should show version data after switching to versions tab', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)

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

  it('should render preview tab label', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)

    renderPage()

    await waitForDataset()

    expect(screen.getByText('预览')).toBeTruthy()
  })

  it('should show file list when preview tab is active', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)
    mockGetVersionFiles.mockResolvedValueOnce([
      {
        fileName: 'data.csv',
        sizeBytes: 1024,
        contentType: 'text/csv',
        lastModified: '2026-05-01T00:00:00Z',
      },
      {
        fileName: 'image.png',
        sizeBytes: 2048,
        contentType: 'image/png',
        lastModified: '2026-05-01T00:00:00Z',
      },
    ])
    mockGetVersionStats.mockResolvedValueOnce({
      versionId: 'v-2',
      versionNumber: 2,
      fileCount: 2,
      totalSizeBytes: 3072,
      fileTypeDistribution: [
        { extension: '.csv', count: 1, totalSizeBytes: 1024 },
        { extension: '.png', count: 1, totalSizeBytes: 2048 },
      ],
    })

    renderPage()

    await waitForDataset()

    const previewTab = screen.getByText('预览')
    await userEvent.click(previewTab)

    await waitFor(() => {
      expect(screen.getByText('data.csv')).toBeTruthy()
      expect(screen.getByText('image.png')).toBeTruthy()
    })

    expect(mockGetVersionFiles).toHaveBeenCalledWith('ds-1', 'v-2')
  })

  it('should show stats when preview tab is active', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)
    mockGetVersionFiles.mockResolvedValueOnce([])
    mockGetVersionStats.mockResolvedValueOnce({
      versionId: 'v-2',
      versionNumber: 2,
      fileCount: 3,
      totalSizeBytes: 1024,
      fileTypeDistribution: [
        { extension: '.csv', count: 2, totalSizeBytes: 512 },
        { extension: '.json', count: 1, totalSizeBytes: 512 },
      ],
    })

    renderPage()

    await waitForDataset()

    const previewTab = screen.getByText('预览')
    await userEvent.click(previewTab)

    await waitFor(() => {
      expect(screen.getByText('.csv(2)')).toBeTruthy()
      expect(screen.getByText('.json(1)')).toBeTruthy()
    })
  })

  it('should show empty state when no files', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)
    mockGetVersionFiles.mockResolvedValueOnce([])
    mockGetVersionStats.mockResolvedValueOnce({
      versionId: 'v-2',
      versionNumber: 2,
      fileCount: 0,
      totalSizeBytes: 0,
      fileTypeDistribution: [],
    })

    renderPage()

    await waitForDataset()

    const previewTab = screen.getByText('预览')
    await userEvent.click(previewTab)

    await waitFor(() => {
      expect(screen.getByText('暂无文件，请先上传文件')).toBeTruthy()
    })
  })

  it('should call download when download button clicked', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)
    mockGetVersionFiles.mockResolvedValueOnce([
      {
        fileName: 'data.csv',
        sizeBytes: 1024,
        contentType: 'text/csv',
        lastModified: '2026-05-01T00:00:00Z',
      },
    ])
    mockGetVersionStats.mockResolvedValueOnce({
      versionId: 'v-2',
      versionNumber: 2,
      fileCount: 1,
      totalSizeBytes: 1024,
      fileTypeDistribution: [{ extension: '.csv', count: 1, totalSizeBytes: 1024 }],
    })
    mockGetFileDownloadUrl.mockResolvedValueOnce('https://minio.example.com/download')

    const openSpy = vi.spyOn(window, 'open').mockImplementation(() => null)

    renderPage()

    await waitForDataset()

    const previewTab = screen.getByText('预览')
    await userEvent.click(previewTab)

    await waitFor(() => {
      expect(screen.getByText('data.csv')).toBeTruthy()
    })

    const downloadBtn = screen.getByText('下载')
    await userEvent.click(downloadBtn)

    await waitFor(() => {
      expect(mockGetFileDownloadUrl).toHaveBeenCalledWith('ds-1', 'v-2', 'data.csv')
      expect(openSpy).toHaveBeenCalledWith('https://minio.example.com/download', '_blank')
    })

    openSpy.mockRestore()
  })
})
