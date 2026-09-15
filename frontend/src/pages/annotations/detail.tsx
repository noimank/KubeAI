import { useState, useCallback } from 'react'
import {
  Breadcrumb,
  Button,
  Descriptions,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { SyncOutlined } from '@ant-design/icons'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { formatDate } from '@/utils/format'
import { useRbacStore } from '@/stores/rbacStore'
import { useAuthStore } from '@/stores/authStore'
import { getAnnotationProjectDetail } from '@/services/annotations'
import {
  cancelAnnotation,
  getAnnotationProjectTasks,
  getAnnotationTaskDetail,
  syncAnnotationProjectTasks,
  unassignAnnotationTasks,
} from '@/services/annotations'
import ProjectInfo from './components/ProjectInfo'
import TaskAssignModal from './components/TaskAssignModal'
import AnnotationPreview from './components/AnnotationPreview'
import type { AnnotationTask } from '@/types/annotation'
import type { ColumnsType } from 'antd/es/table'

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  unassigned: { label: '未分配', color: 'default' },
  assigned: { label: '已分配', color: 'processing' },
  in_progress: { label: '进行中', color: 'blue' },
  completed: { label: '已完成', color: 'success' },
}

function extractTaskFileName(task: AnnotationTask): string {
  const data = task.data ?? {}
  return (data.kubeaiFileName as string | undefined) || '-'
}

export default function AnnotationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const currentUserId = useAuthStore((s) => s.user?.id)
  const canManage = hasPermission('annotations:manage')

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const [assignMode, setAssignMode] = useState<'assign' | 'batch'>('assign')
  const [assignTaskIds, setAssignTaskIds] = useState<string[]>([])
  const [assignTitle, setAssignTitle] = useState<string>()
  const [previewTask, setPreviewTask] = useState<AnnotationTask | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)

  const { data: project } = useQuery({
    queryKey: ['annotationProject', id],
    queryFn: () => getAnnotationProjectDetail(id!),
    enabled: !!id,
  })

  const queryClient = useQueryClient()

  const syncMutation = useMutation({
    mutationFn: () => syncAnnotationProjectTasks(id!),
    onSuccess: (res) => {
      getMessageInstance()?.success(res.message || '同步完成')
      queryClient.invalidateQueries({ queryKey: ['annotationProject', id] })
      queryClient.invalidateQueries({ queryKey: ['annotationProjectTasks', id] })
    },
  })

  const { data: tasksData, isLoading: tasksLoading } = useQuery({
    queryKey: ['annotationProjectTasks', id, page, pageSize, statusFilter],
    queryFn: () =>
      getAnnotationProjectTasks(id!, {
        current: page,
        pageSize,
        status: statusFilter,
      }),
    enabled: !!id,
  })

  const handleAssign = useCallback(() => {
    setAssignMode('assign')
    setAssignTaskIds(selectedRowKeys)
    setAssignTitle(undefined)
    setAssignModalOpen(true)
  }, [selectedRowKeys])

  const handleReassign = useCallback((task: AnnotationTask) => {
    setAssignMode('assign')
    setAssignTaskIds([task.id])
    setAssignTitle(task.assignedTo ? '修改分配人' : '分配任务')
    setAssignModalOpen(true)
  }, [])

  const handleBatchAssign = useCallback(() => {
    setAssignMode('batch')
    setAssignTaskIds([])
    setAssignTitle(undefined)
    setAssignModalOpen(true)
  }, [])

  const unassignMutation = useMutation({
    mutationFn: (taskIds: string[]) => unassignAnnotationTasks(id!, { taskIds }),
    onSuccess: (res) => {
      getMessageInstance()?.success(res.message || '取消分配成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProjectTasks', id] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTasks'] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTaskSummary'] })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (taskId: string) => cancelAnnotation(taskId),
    onSuccess: () => {
      getMessageInstance()?.success('标注已取消')
      queryClient.invalidateQueries({ queryKey: ['annotationProject', id] })
      queryClient.invalidateQueries({ queryKey: ['annotationProjectTasks', id] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTasks'] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTaskSummary'] })
      if (project) {
        queryClient.invalidateQueries({
          queryKey: ['version-files', project.datasetId, project.datasetVersionId],
        })
      }
    },
  })

  const unassignedCount = tasksData?.items?.filter((t) => t.status === 'unassigned').length ?? 0
  const selectedTasks = tasksData?.items?.filter((task) => selectedRowKeys.includes(task.id)) ?? []
  const selectedAssignedTaskIds = selectedTasks
    .filter((task) => task.status === 'assigned')
    .map((task) => task.id)

  const handlePreview = useCallback(async (task: AnnotationTask) => {
    setPreviewLoading(true)
    setPreviewTask(task)
    try {
      const detail = await getAnnotationTaskDetail(task.id)
      setPreviewTask(detail)
    } catch {
      // interceptor handles error toast
    } finally {
      setPreviewLoading(false)
    }
  }, [])

  const columns: ColumnsType<AnnotationTask> = [
    {
      title: '文件名',
      dataIndex: 'data',
      width: 240,
      ellipsis: true,
      render: (_, record) => {
        return extractTaskFileName(record)
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: string) => {
        const info = STATUS_MAP[status] || { label: status, color: 'default' }
        return <Tag color={info.color}>{info.label}</Tag>
      },
    },
    {
      title: '分配人',
      dataIndex: 'assignedToName',
      width: 120,
      render: (name: string | undefined) => name || '-',
    },
    {
      title: '操作',
      width: 200,
      render: (_: unknown, record) => {
        const canCancel = record.status === 'completed' && record.assignedTo === currentUserId
        return (
          <Space size="small">
            <Button type="link" size="small" onClick={() => handlePreview(record)}>
              预览
            </Button>
            {canManage && (record.status === 'unassigned' || record.status === 'assigned') && (
              <Button type="link" size="small" onClick={() => handleReassign(record)}>
                {record.assignedTo ? '改派' : '分配'}
              </Button>
            )}
            {canManage && record.status === 'assigned' && (
              <Popconfirm
                title="确认取消分配该任务？"
                okText="确认"
                cancelText="取消"
                onConfirm={() => unassignMutation.mutate([record.id])}
              >
                <Button type="link" size="small" danger loading={unassignMutation.isPending}>
                  取消
                </Button>
              </Popconfirm>
            )}
            {canCancel && (
              <Popconfirm
                title="确认取消标注？"
                description="将删除 annotations/<file>.json 并把任务回到「进行中」"
                okText="确认"
                cancelText="取消"
                onConfirm={() => cancelMutation.mutate(record.id)}
              >
                <Button
                  type="link"
                  size="small"
                  danger
                  loading={cancelMutation.isPending && cancelMutation.variables === record.id}
                >
                  取消标注
                </Button>
              </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  if (!project) return null

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Breadcrumb
          items={[{ title: <Link to="/annotations">标注管理</Link> }, { title: project.name }]}
        />
      </div>

      <ProjectInfo project={project} />

      <div
        style={{
          marginBottom: 12,
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <Space>
          <span style={{ fontWeight: 500 }}>任务列表</span>
          <Select
            placeholder="状态筛选"
            allowClear
            style={{ width: 140 }}
            value={statusFilter}
            onChange={(v) => {
              setStatusFilter(v)
              setPage(1)
              setSelectedRowKeys([])
            }}
            options={[
              { label: '未分配', value: 'unassigned' },
              { label: '已分配', value: 'assigned' },
              { label: '进行中', value: 'in_progress' },
              { label: '已完成', value: 'completed' },
            ]}
          />
        </Space>
        {canManage && (
          <Space>
            <Button
              icon={<SyncOutlined />}
              onClick={() => syncMutation.mutate()}
              loading={syncMutation.isPending}
            >
              同步新数据
            </Button>
            <Button onClick={handleBatchAssign}>均匀分配</Button>
            {selectedAssignedTaskIds.length > 0 && (
              <Popconfirm
                title={`确认取消分配 ${selectedAssignedTaskIds.length} 个任务？`}
                okText="确认"
                cancelText="取消"
                onConfirm={() => unassignMutation.mutate(selectedAssignedTaskIds)}
              >
                <Button danger loading={unassignMutation.isPending}>
                  取消分配 ({selectedAssignedTaskIds.length})
                </Button>
              </Popconfirm>
            )}
            {selectedRowKeys.length > 0 && (
              <Button type="primary" onClick={handleAssign}>
                分配给... ({selectedRowKeys.length})
              </Button>
            )}
          </Space>
        )}
      </div>

      <Table<AnnotationTask>
        rowKey="id"
        columns={columns}
        dataSource={tasksData?.items}
        loading={tasksLoading}
        rowSelection={
          canManage
            ? {
                selectedRowKeys,
                onChange: (keys) => setSelectedRowKeys(keys as string[]),
                getCheckboxProps: (record) => ({
                  disabled: record.status !== 'unassigned' && record.status !== 'assigned',
                }),
              }
            : undefined
        }
        pagination={{
          current: page,
          pageSize,
          total: tasksData?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100'],
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
            setSelectedRowKeys([])
          },
        }}
      />

      <TaskAssignModal
        open={assignModalOpen}
        onClose={() => setAssignModalOpen(false)}
        projectId={id!}
        mode={assignMode}
        selectedTaskIds={assignTaskIds}
        unassignedCount={unassignedCount}
        title={assignTitle}
      />

      <TaskPreviewModal
        task={previewTask}
        open={!!previewTask}
        loading={previewLoading}
        onClose={() => setPreviewTask(null)}
      />
    </div>
  )
}

function TaskPreviewModal({
  task,
  open,
  loading,
  onClose,
}: {
  task: AnnotationTask | null
  open: boolean
  loading: boolean
  onClose: () => void
}) {
  const fileName = task ? extractTaskFileName(task) : '-'
  const statusInfo = task
    ? STATUS_MAP[task.status] || { label: task.status, color: 'default' }
    : null

  return (
    <Modal
      title="任务预览"
      open={open}
      onCancel={onClose}
      footer={null}
      width={880}
      loading={loading}
      destroyOnHidden
    >
      {task && (
        <Descriptions size="small" bordered column={2} style={{ marginBottom: 16 }}>
          <Descriptions.Item label="文件名" span={2}>
            <Typography.Text style={{ wordBreak: 'break-all' }}>{fileName}</Typography.Text>
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            {statusInfo ? <Tag color={statusInfo.color}>{statusInfo.label}</Tag> : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="分配人">{task.assignedToName || '-'}</Descriptions.Item>
          <Descriptions.Item label="项目">{task.projectName || '-'}</Descriptions.Item>
          <Descriptions.Item label="提交时间">
            {task.submittedAt ? formatDate(task.submittedAt) : '-'}
          </Descriptions.Item>
        </Descriptions>
      )}

      {task && (
        <AnnotationPreview
          task={task}
          result={task.result ?? null}
          annotationPayload={task.annotationPayload ?? null}
        />
      )}
    </Modal>
  )
}
