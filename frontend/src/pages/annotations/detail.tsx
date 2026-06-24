import { useState, useCallback } from 'react'
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Image,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import { RedoOutlined, SyncOutlined } from '@ant-design/icons'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { formatDate } from '@/utils/format'
import { useRbacStore } from '@/stores/rbacStore'
import { getAnnotationProjectDetail } from '@/services/annotations'
import {
  getAnnotationProjectTasks,
  getAnnotationTaskDetail,
  retryCallback,
  syncAnnotationProjectTasks,
  unassignAnnotationTasks,
} from '@/services/annotations'
import ProjectInfo from './components/ProjectInfo'
import TaskAssignModal from './components/TaskAssignModal'
import type { AnnotationTask, AnnotationCallbackStatus } from '@/types/annotation'
import type { ColumnsType } from 'antd/es/table'
import { appendAuthToken } from '@/utils/constants'

const { Text } = Typography

const CALLBACK_STATUS_MAP: Record<AnnotationCallbackStatus, { label: string; color: string }> = {
  pending: { label: '等待回流', color: 'processing' },
  running: { label: '回流中', color: 'processing' },
  succeeded: { label: '回流成功', color: 'success' },
  failed: { label: '回流失败', color: 'error' },
}

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

  const retryMutation = useMutation({
    mutationFn: () => retryCallback(id!),
    onSuccess: () => {
      getMessageInstance()?.success('回流重试已触发')
      queryClient.invalidateQueries({ queryKey: ['annotationProject', id] })
    },
  })

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
      width: 180,
      render: (_: unknown, record) => {
        if (!canManage) return null
        return (
          <Space size="small">
            <Button type="link" size="small" onClick={() => handlePreview(record)}>
              预览
            </Button>
            {(record.status === 'unassigned' || record.status === 'assigned') && (
              <Button type="link" size="small" onClick={() => handleReassign(record)}>
                {record.assignedTo ? '改派' : '分配'}
              </Button>
            )}
            {record.status === 'assigned' && (
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

      {project.callbackStatus && project.callbackStatus !== 'pending' && (
        <CallbackStatusCard
          status={project.callbackStatus}
          error={project.callbackError}
          progress={project.callbackProgress}
          versionId={project.callbackVersionId}
          datasetId={project.datasetId}
          onRetry={() => retryMutation.mutate()}
          retrying={retryMutation.isPending}
        />
      )}

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
  const data = task?.data ?? {}
  const fileName = task ? extractTaskFileName(task) : '-'
  const statusInfo = task
    ? STATUS_MAP[task.status] || { label: task.status, color: 'default' }
    : null
  const imageEntry = Object.entries(data).find(
    ([key, value]) =>
      !key.startsWith('kubeai') && typeof value === 'string' && /^(\/|https?:\/\/)/.test(value),
  )
  const textEntry = Object.entries(data).find(
    ([key, value]) =>
      !key.startsWith('kubeai') && typeof value === 'string' && !/^(\/|https?:\/\/)/.test(value),
  )

  return (
    <Modal
      title="任务预览"
      open={open}
      onCancel={onClose}
      footer={null}
      width={820}
      loading={loading}
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
          <Descriptions.Item label="Label Studio 任务 ID">
            {task.labelStudioTaskId}
          </Descriptions.Item>
          <Descriptions.Item label="项目">{task.projectName || '-'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDate(task.createdAt)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{formatDate(task.updatedAt)}</Descriptions.Item>
        </Descriptions>
      )}

      {imageEntry && (
        <div style={{ marginBottom: 16, textAlign: 'center' }}>
          <Image src={appendAuthToken(imageEntry[1] as string)} style={{ maxHeight: 420 }} />
        </div>
      )}
      {textEntry && (
        <Card size="small" style={{ marginBottom: 16 }}>
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
            {textEntry[1] as string}
          </Typography.Paragraph>
        </Card>
      )}
    </Modal>
  )
}

function CallbackStatusCard({
  status,
  error,
  progress,
  versionId,
  datasetId,
  onRetry,
  retrying,
}: {
  status: AnnotationCallbackStatus
  error?: string
  progress?: number
  versionId?: string
  datasetId: string
  onRetry: () => void
  retrying: boolean
}) {
  const info = CALLBACK_STATUS_MAP[status] || { label: status, color: 'default' }

  return (
    <Card style={{ marginBottom: 16 }} size="small">
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space>
          <Text strong>回流状态：</Text>
          <Tag color={info.color}>{info.label}</Tag>
          {status === 'running' && progress != null && (
            <Progress percent={progress} size="small" style={{ width: 200 }} />
          )}
        </Space>
        {status === 'succeeded' && versionId && (
          <Space>
            <Text type="secondary">回流版本：</Text>
            <Link to={`/datasets/${datasetId}`}>查看数据集</Link>
          </Space>
        )}
        {status === 'failed' && error && (
          <Alert
            type="error"
            message="回流失败"
            description={error}
            showIcon
            style={{ marginTop: 4 }}
          />
        )}
        {status === 'failed' && (
          <Button
            icon={<RedoOutlined />}
            onClick={onRetry}
            loading={retrying}
            size="small"
            style={{ marginTop: 4 }}
          >
            重试回流
          </Button>
        )}
      </Space>
    </Card>
  )
}
