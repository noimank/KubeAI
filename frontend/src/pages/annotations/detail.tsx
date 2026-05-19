import { useState, useCallback } from 'react'
import { Button, Select, Space, Table, Tag } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useRbacStore } from '@/stores/rbacStore'
import { getAnnotationProjectDetail } from '@/services/annotations'
import { getAnnotationProjectTasks } from '@/services/annotations'
import ProjectInfo from './components/ProjectInfo'
import TaskAssignModal from './components/TaskAssignModal'
import type { AnnotationTask } from '@/types/annotation'
import type { ColumnsType } from 'antd/es/table'

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  unassigned: { label: '未分配', color: 'default' },
  assigned: { label: '已分配', color: 'processing' },
  in_progress: { label: '进行中', color: 'blue' },
  completed: { label: '已完成', color: 'success' },
}

export default function AnnotationDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canManage = hasPermission('annotations:manage')

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string | undefined>()
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [assignModalOpen, setAssignModalOpen] = useState(false)
  const [assignMode, setAssignMode] = useState<'assign' | 'batch'>('assign')

  const { data: project } = useQuery({
    queryKey: ['annotationProject', id],
    queryFn: () => getAnnotationProjectDetail(id!),
    enabled: !!id,
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
    setAssignModalOpen(true)
  }, [])

  const handleBatchAssign = useCallback(() => {
    setAssignMode('batch')
    setAssignModalOpen(true)
  }, [])

  const unassignedCount = tasksData?.items?.filter((t) => t.status === 'unassigned').length ?? 0

  const columns: ColumnsType<AnnotationTask> = [
    {
      title: '任务预览',
      width: 240,
      ellipsis: true,
      render: (_, record) => {
        const data = record.data
        const image = data?.image as string | undefined
        const text = data?.text as string | undefined
        const fileName = data?.file_name as string | undefined
        if (image) {
          return (
            <img
              src={image}
              alt="preview"
              style={{ width: 40, height: 40, objectFit: 'cover', borderRadius: 4, marginRight: 8 }}
            />
          )
        }
        return fileName || text?.slice(0, 40) || '-'
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
      width: 80,
      render: (_: unknown, record) => {
        if (!canManage) return null
        return (
          <Button
            type="link"
            size="small"
            disabled={record.status === 'unassigned'}
            onClick={() => navigate(`/annotations/projects/${record.projectId}/workspace`)}
          >
            预览
          </Button>
        )
      },
    },
  ]

  if (!project) return null

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/annotations')}>
          返回
        </Button>
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
            <Button onClick={handleBatchAssign}>均匀分配</Button>
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
        selectedTaskIds={selectedRowKeys}
        unassignedCount={unassignedCount}
      />
    </div>
  )
}
