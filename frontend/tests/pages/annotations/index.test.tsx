import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AnnotationsPage from '@/pages/annotations'
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

vi.mock('@/services/annotations', () => ({
  getAnnotationProjects: vi.fn(),
  deleteAnnotationProject: vi.fn(),
  createAnnotationProject: vi.fn(),
  getAnnotationTemplates: vi.fn(),
  getMyAnnotationTasks: vi.fn(),
  getMyAnnotationTaskSummary: vi.fn(),
  cancelAnnotation: vi.fn(),
}))

vi.mock('@/services/datasets', () => ({
  getDatasets: vi.fn(),
  getDatasetDetail: vi.fn(),
}))

vi.mock('@/utils/messageHolder', () => ({
  getMessageInstance: vi.fn(() => ({
    success: vi.fn(),
    error: vi.fn(),
  })),
}))

const mockGetAnnotationProjects = vi.mocked(
  await import('@/services/annotations'),
).getAnnotationProjects
const mockGetMyAnnotationTasks = vi.mocked(
  await import('@/services/annotations'),
).getMyAnnotationTasks
const mockGetMyAnnotationTaskSummary = vi.mocked(
  await import('@/services/annotations'),
).getMyAnnotationTaskSummary

const mockProject = {
  id: 'proj-1',
  name: '测试标注项目',
  description: 'test project',
  datasetId: 'ds-1',
  datasetVersionId: 'dv-1',
  annotationType: 'image_classification' as const,
  totalTasks: 10,
  completedTasks: 3,
  status: 'active' as const,
  createdBy: 'u-1',
  createdAt: '2026-05-01T12:00:00Z',
  updatedAt: '2026-05-01T12:00:00Z',
  tenantId: 't-1',
  datasetName: '测试数据集',
  datasetVersionNumber: 1,
  progressPercent: 30,
}

const mockTask = {
  id: 'task-1',
  projectId: 'proj-1',
  labelStudioTaskId: 1,
  data: {},
  status: 'assigned' as const,
  projectName: '测试标注项目',
  annotationType: 'image_classification' as const,
  createdAt: '2026-05-01T12:00:00Z',
  updatedAt: '2026-05-01T12:00:00Z',
}

const emptyPage = { items: [], total: 0, page: 1, pageSize: 20 }

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AnnotationsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('AnnotationsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetAnnotationProjects.mockResolvedValue(emptyPage)
    mockGetMyAnnotationTasks.mockResolvedValue(emptyPage)
    mockGetMyAnnotationTaskSummary.mockResolvedValue([])
  })

  it('should render project list tab for admin', async () => {
    useRbacStore.getState().setRole('admin')
    mockGetAnnotationProjects.mockResolvedValue({
      items: [mockProject],
      total: 1,
      page: 1,
      pageSize: 20,
    })

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('测试标注项目')).toBeTruthy()
    })
    expect(screen.getByText('项目列表')).toBeTruthy()
    expect(screen.getByText('我的任务')).toBeTruthy()
  })

  it('should show create button for user with manage permission', async () => {
    useRbacStore.getState().setRole('admin')

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('创建标注项目')).toBeTruthy()
    })
  })

  it('should not show create button for annotator', async () => {
    useRbacStore.getState().setRole('annotator')

    renderPage()

    await waitFor(() => {
      expect(screen.queryByText('创建标注项目')).toBeNull()
    })
    // Annotator should see my-task list directly (no tabs)
    expect(screen.queryByText('项目列表')).toBeNull()
  })

  it('should show empty state when no projects', async () => {
    useRbacStore.getState().setRole('admin')
    mockGetAnnotationProjects.mockResolvedValue(emptyPage)

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('还没有标注项目')).toBeTruthy()
    })
  })

  it('should show create button in empty state for admin', async () => {
    useRbacStore.getState().setRole('admin')
    mockGetAnnotationProjects.mockResolvedValue(emptyPage)

    renderPage()

    await waitFor(() => {
      const emptyCreateBtns = screen.getAllByText('选择数据集创建标注任务')
      expect(emptyCreateBtns.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('should not show create button in empty state for annotator', async () => {
    useRbacStore.getState().setRole('annotator')

    renderPage()

    await waitFor(() => {
      expect(screen.queryByText('选择数据集创建标注任务')).toBeNull()
    })
  })

  it('should search by keyword', async () => {
    useRbacStore.getState().setRole('admin')
    mockGetAnnotationProjects.mockResolvedValue(emptyPage)

    renderPage()

    const searchInput = await screen.findByPlaceholderText('搜索标注项目名称')
    await userEvent.type(searchInput, 'test{Enter}')

    await waitFor(() => {
      expect(mockGetAnnotationProjects).toHaveBeenCalledWith(
        expect.objectContaining({ keyword: 'test' }),
      )
    })
  })

  it('should show empty state for my tasks', async () => {
    useRbacStore.getState().setRole('annotator')
    mockGetMyAnnotationTasks.mockResolvedValue(emptyPage)
    mockGetMyAnnotationTaskSummary.mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('暂无分配的标注任务')).toBeTruthy()
    })
  })

  it('should render my tasks list for annotator', async () => {
    useRbacStore.getState().setRole('annotator')
    mockGetMyAnnotationTasks.mockResolvedValue({
      items: [mockTask],
      total: 1,
      page: 1,
      pageSize: 20,
    })
    mockGetMyAnnotationTaskSummary.mockResolvedValue([])

    renderPage()

    await waitFor(() => {
      expect(screen.getByText('测试标注项目')).toBeTruthy()
    })
  })
})
