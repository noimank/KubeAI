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
  downloadFile: vi.fn(),
  fetchFileBlob: vi.fn(),
  createBlobUrl: vi.fn(() => 'blob:fake'),
  revokeBlobUrl: vi.fn(),
  deleteVersionFile: vi.fn(),
}))

const mockGetDatasetDetail = vi.mocked(await import('@/services/datasets')).getDatasetDetail
const mockGetVersionFiles = vi.mocked(await import('@/services/datasets')).getVersionFiles
const mockGetVersionStats = vi.mocked(await import('@/services/datasets')).getVersionStats
const mockGetFileDownloadUrl = vi.mocked(await import('@/services/datasets')).getFileDownloadUrl
const mockDownloadFile = vi.mocked(await import('@/services/datasets')).downloadFile
const mockFetchFileBlob = vi.mocked(await import('@/services/datasets')).fetchFileBlob

const FILE_ID_1 = '11111111-1111-1111-1111-111111111111'
const FILE_ID_2 = '22222222-2222-2222-2222-222222222222'

const mockFilesPage = {
  items: [
    {
      fileId: FILE_ID_1,
      fileName: 'data.csv',
      relativePath: 'data.csv',
      fileSize: 1024,
      contentType: 'text/csv',
      uploadedAt: '2026-05-01T00:00:00Z',
      isAnnotated: false,
    },
    {
      fileId: FILE_ID_2,
      fileName: 'image.png',
      relativePath: 'image.png',
      fileSize: 2048,
      contentType: 'image/png',
      uploadedAt: '2026-05-01T00:00:00Z',
      isAnnotated: false,
    },
  ],
  total: 2,
  page: 1,
  pageSize: 50,
}

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

  it('should show file list when preview tab is active and not eagerly fetch blobs', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)
    mockGetVersionFiles.mockResolvedValueOnce(mockFilesPage)
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

    expect(mockGetVersionFiles).toHaveBeenCalledWith(
      'ds-1',
      'v-2',
      expect.objectContaining({ page: 1, pageSize: 50 }),
    )
    // 关键: 表格渲染不应触 fetchFileBlob
    expect(mockFetchFileBlob).not.toHaveBeenCalled()
  })

  it('should show stats when preview tab is active', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)
    mockGetVersionFiles.mockResolvedValueOnce({ ...mockFilesPage, items: [] })
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
    mockGetVersionFiles.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      pageSize: 50,
    })
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
    mockGetVersionFiles.mockResolvedValueOnce({
      items: [mockFilesPage.items[0]],
      total: 1,
      page: 1,
      pageSize: 50,
    })
    mockGetVersionStats.mockResolvedValueOnce({
      versionId: 'v-2',
      versionNumber: 2,
      fileCount: 1,
      totalSizeBytes: 1024,
      fileTypeDistribution: [{ extension: '.csv', count: 1, totalSizeBytes: 1024 }],
    })
    mockGetFileDownloadUrl.mockResolvedValueOnce('https://minio.example.com/download')

    renderPage()

    await waitForDataset()

    const previewTab = screen.getByText('预览')
    await userEvent.click(previewTab)

    await waitFor(() => {
      expect(screen.getByText('data.csv')).toBeTruthy()
    })

    const downloadBtn = screen.getByRole('button', { name: '下载' })
    await userEvent.click(downloadBtn)

    await waitFor(() => {
      expect(mockDownloadFile).toHaveBeenCalledWith('ds-1', 'v-2', 'data.csv')
    })
  })

  it('should only fetch blob after user clicks preview icon', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)
    mockGetVersionFiles.mockResolvedValueOnce(mockFilesPage)
    mockGetVersionStats.mockResolvedValueOnce({
      versionId: 'v-2',
      versionNumber: 2,
      fileCount: 2,
      totalSizeBytes: 3072,
      fileTypeDistribution: [],
    })
    mockFetchFileBlob.mockResolvedValueOnce(new Blob(['fake'], { type: 'image/png' }))

    renderPage()

    await waitForDataset()

    const previewTab = screen.getByText('预览')
    await userEvent.click(previewTab)

    await waitFor(() => {
      expect(screen.getByText('image.png')).toBeTruthy()
    })

    // 此时还没点眼睛图标, fetchFileBlob 不应触发
    expect(mockFetchFileBlob).not.toHaveBeenCalled()

    // 点预览图标 (image.png 行) - 用 icon className 找按钮
    const imageRow = screen.getByText('image.png').closest('tr')!
    const previewBtn = imageRow.querySelector('button') as HTMLButtonElement
    expect(previewBtn).toBeTruthy()
    await userEvent.click(previewBtn)

    await waitFor(() => {
      expect(mockFetchFileBlob).toHaveBeenCalledWith('ds-1', 'v-2', 'image.png')
    })
  })

  it('should render annotation column from list payload (no per-row fetch)', async () => {
    mockGetDatasetDetail.mockResolvedValueOnce(mockDataset)
    mockGetVersionFiles.mockResolvedValueOnce({
      ...mockFilesPage,
      items: [
        { ...mockFilesPage.items[0], isAnnotated: true },
        { ...mockFilesPage.items[1], isAnnotated: false },
      ],
    })
    mockGetVersionStats.mockResolvedValueOnce({
      versionId: 'v-2',
      versionNumber: 2,
      fileCount: 2,
      totalSizeBytes: 3072,
      fileTypeDistribution: [],
      annotatedCount: 1,
    })

    renderPage()

    await waitForDataset()

    const previewTab = screen.getByText('预览')
    await userEvent.click(previewTab)

    await waitFor(() => {
      // 第一行已标注 -> Tag
      const annotatedRows = screen.getAllByText('已标注')
      expect(annotatedRows.length).toBe(1)
    })

    // 关键: 列表数据已经带 isAnnotated, 组件不应再调 getFileAnnotation
    // (该函数已从 services 中删除, 任何调用都会 throw)
  })
})
