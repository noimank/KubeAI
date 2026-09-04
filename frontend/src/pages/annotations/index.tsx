import { useState, useCallback } from 'react'
import { Button, Input, Select, Tabs } from 'antd'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import {
  deleteAnnotationProject,
  getAnnotationProjects,
  retryAnnotationProject,
} from '@/services/annotations'
import AnnotationProjectTable from './components/AnnotationProjectTable'
import AnnotationTemplatesTab from './components/AnnotationTemplatesTab'
import CreateProjectModal from './components/CreateProjectModal'
import MyTaskList from './components/MyTaskList'
import { STATUS_MAP } from './utils/projectStatus'

export default function AnnotationsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')
  const [statusFilter, setStatusFilter] = useState<string>()
  const [createModalOpen, setCreateModalOpen] = useState(false)

  // My tasks pagination (separate from project list)
  const [myPage, setMyPage] = useState(1)
  const [myPageSize, setMyPageSize] = useState(20)

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canManage = hasPermission('annotations:manage')
  const isAnnotator = hasPermission('annotations:read') && !canManage
  const canReadTemplates = hasPermission('annotation_templates:read')
  const canWriteTemplates = hasPermission('annotation_templates:write') || canManage

  const { data, isLoading } = useQuery({
    queryKey: ['annotationProjects', page, pageSize, keyword, statusFilter],
    queryFn: () =>
      getAnnotationProjects({ current: page, pageSize, keyword, status: statusFilter }),
  })

  const [retryingId, setRetryingId] = useState<string | null>(null)

  const retryMutation = useMutation({
    mutationFn: (projectId: string) => retryAnnotationProject(projectId),
    onMutate: (projectId) => setRetryingId(projectId),
    onSettled: () => setRetryingId(null),
    onSuccess: () => {
      getMessageInstance()?.success('项目重试已启动')
      queryClient.invalidateQueries({ queryKey: ['annotationProjects'] })
    },
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handlePageChange = useCallback((p: number, ps: number) => {
    setPage(p)
    setPageSize(ps)
  }, [])

  const handleMyPageChange = useCallback((p: number, ps: number) => {
    setMyPage(p)
    setMyPageSize(ps)
  }, [])

  const handleDelete = async (id: string) => {
    try {
      await deleteAnnotationProject(id)
      getMessageInstance()?.success('标注项目删除成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProjects'] })
    } catch {
      // interceptor handles error toast
    }
  }

  // Annotator-only view: show "我的任务" directly
  if (isAnnotator) {
    return (
      <div style={{ padding: 0 }}>
        <MyTaskList page={myPage} pageSize={myPageSize} onPageChange={handleMyPageChange} />
      </div>
    )
  }

  const tabItems = [
    {
      key: 'projects',
      label: '项目列表',
      children: (
        <>
          <div
            style={{
              marginBottom: 16,
              display: 'flex',
              justifyContent: 'space-between',
              gap: 12,
            }}
          >
            <div style={{ display: 'flex', gap: 12 }}>
              <Input.Search
                placeholder="搜索标注项目名称"
                allowClear
                style={{ width: 280 }}
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onSearch={handleSearch}
                prefix={<SearchOutlined />}
              />
              <Select
                placeholder="状态筛选"
                allowClear
                style={{ width: 140 }}
                value={statusFilter}
                onChange={(v) => {
                  setStatusFilter(v)
                  setPage(1)
                }}
                options={Object.entries(STATUS_MAP).map(([value, { label }]) => ({
                  label,
                  value,
                }))}
              />
            </div>
            {canManage && (
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setCreateModalOpen(true)}
              >
                创建标注项目
              </Button>
            )}
          </div>

          <AnnotationProjectTable
            data={data?.items}
            loading={isLoading}
            total={data?.total ?? 0}
            page={page}
            pageSize={pageSize}
            onPageChange={handlePageChange}
            onDelete={handleDelete}
            onRetry={(id) => retryMutation.mutate(id)}
            retryingId={retryingId}
            canManage={canManage}
            onCreateClick={() => setCreateModalOpen(true)}
          />
        </>
      ),
    },
    {
      key: 'my-tasks',
      label: '我的任务',
      children: (
        <MyTaskList page={myPage} pageSize={myPageSize} onPageChange={handleMyPageChange} />
      ),
    },
  ]

  if (canReadTemplates) {
    tabItems.push({
      key: 'templates',
      label: '标注模板',
      children: <AnnotationTemplatesTab canWrite={canWriteTemplates} />,
    })
  }

  // Admin/MLOps view: Tabs with "项目列表", "我的任务", and (gated) "标注模板"
  return (
    <div style={{ padding: 0 }}>
      <Tabs defaultActiveKey="projects" items={tabItems} />

      <CreateProjectModal open={createModalOpen} onClose={() => setCreateModalOpen(false)} />
    </div>
  )
}
