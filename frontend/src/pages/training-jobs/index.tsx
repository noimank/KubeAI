import { useState, useCallback } from 'react'
import { Button, Empty, Input, Popconfirm, Segmented, Space, Table, Tag } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { formatDate } from '@/utils/format'
import { useRbacStore } from '@/stores/rbacStore'
import {
  getTrainingJob,
  getTrainingJobs,
  stopTrainingJob,
  deleteTrainingJob,
} from '@/services/training-jobs'
import type { TrainingJob, TrainingJobStatus } from '@/types/training-job'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '等待中' },
  queued: { color: 'warning', text: '排队中' },
  initializing: { color: 'processing', text: '初始化' },
  running: { color: 'processing', text: '运行中' },
  succeeded: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '排队中', value: 'queued' },
  { label: '运行中', value: 'running' },
  { label: '已完成', value: 'succeeded' },
  { label: '已失败', value: 'failed' },
  { label: '已停止', value: 'stopped' },
]

function formatDuration(start?: string, end?: string): string {
  if (!start) return '—'
  const startDate = new Date(start)
  const endDate = end ? new Date(end) : new Date()
  const diffMs = endDate.getTime() - startDate.getTime()
  if (diffMs < 0) return '—'
  const hours = Math.floor(diffMs / 3600000)
  const minutes = Math.floor((diffMs % 3600000) / 60000)
  const seconds = Math.floor((diffMs % 60000) / 1000)
  if (hours > 0) return `${hours}h ${minutes}m`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

export default function TrainingJobsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState('')
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('training_jobs:write')

  const { data, isLoading } = useQuery({
    queryKey: ['trainingJobs', page, pageSize, statusFilter, keyword],
    queryFn: () =>
      getTrainingJobs({
        current: page,
        pageSize,
        status: statusFilter || undefined,
        name: keyword,
      }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const hasActive = items.some((j) =>
        ['pending', 'queued', 'initializing', 'running'].includes(j.status),
      )
      return hasActive ? 5000 : false
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopTrainingJob,
    onSuccess: () => {
      getMessageInstance()?.success('任务已停止')
      queryClient.invalidateQueries({ queryKey: ['trainingJobs'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteTrainingJob,
    onSuccess: () => {
      getMessageInstance()?.success('任务已删除')
      queryClient.invalidateQueries({ queryKey: ['trainingJobs'] })
    },
  })

  const refreshMutation = useMutation({
    mutationFn: (id: string) => getTrainingJob(id),
    onSuccess: () => {
      getMessageInstance()?.success('状态已刷新')
      queryClient.invalidateQueries({ queryKey: ['trainingJobs'] })
    },
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const columns: ColumnsType<TrainingJob> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 220,
      ellipsis: true,
      fixed: 'left',
      render: (name: string, record: TrainingJob) => (
        <Link to={`/training-jobs/${record.id}`}>{name}</Link>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (val: TrainingJobStatus) => {
        const cfg = STATUS_CONFIG[val] || { color: 'default', text: val }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: 'GPU',
      dataIndex: 'gpuCount',
      width: 80,
      render: (val: number) => `${val} 张`,
    },
    {
      title: 'Worker',
      dataIndex: 'workerCount',
      width: 100,
      render: (val: number) =>
        val > 1 ? (
          <span>
            {val} <Tag color="blue">分布式</Tag>
          </span>
        ) : (
          '—'
        ),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
      render: (v: string) => formatDate(v),
    },
    {
      title: '来源',
      dataIndex: 'source',
      width: 100,
      render: (val: string) => {
        if (val === 'manual') return <Tag>手动创建</Tag>
        if (val === 'dev_environment') return <Tag color="blue">开发环境</Tag>
        if (val === 'experiment_reproduction') return <Tag color="green">实验复现</Tag>
        if (val === 'tuning') return <Tag color="purple">超参调优</Tag>
        return null
      },
    },
    {
      title: '运行时长',
      key: 'duration',
      width: 120,
      render: (_: unknown, record: TrainingJob) =>
        formatDuration(record.startedAt, record.finishedAt),
    },
    {
      title: '操作',
      width: 260,
      render: (_: unknown, record: TrainingJob) => (
        <Space size="small">
          <Link to={`/training-jobs/${record.id}`}>
            <Button type="link" size="small">
              详情
            </Button>
          </Link>
          <Button
            type="link"
            size="small"
            icon={<ReloadOutlined />}
            loading={refreshMutation.isPending && refreshMutation.variables === record.id}
            onClick={() => refreshMutation.mutate(record.id)}
          >
            刷新
          </Button>
          {canWrite && ['running', 'queued', 'pending'].includes(record.status) && (
            <Popconfirm
              title="确认停止该任务？"
              description="停止后正在运行的训练将被终止"
              onConfirm={() => stopMutation.mutate(record.id)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>
                停止
              </Button>
            </Popconfirm>
          )}
          {canWrite && ['succeeded', 'failed', 'stopped'].includes(record.status) && (
            <Popconfirm
              title="确认删除该任务？"
              description="删除后将无法恢复"
              onConfirm={() => deleteMutation.mutate(record.id)}
              okText="确认"
              cancelText="取消"
            >
              <Button
                type="link"
                size="small"
                danger
                loading={deleteMutation.isPending && deleteMutation.variables === record.id}
              >
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Space>
          <Segmented
            options={STATUS_TABS}
            value={statusFilter}
            onChange={(val) => {
              setStatusFilter(val as string)
              setPage(1)
            }}
          />
          <Input.Search
            placeholder="搜索任务名称"
            allowClear
            style={{ width: 280 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
            prefix={<SearchOutlined />}
          />
        </Space>
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => queryClient.invalidateQueries({ queryKey: ['trainingJobs'] })}
          >
            刷新
          </Button>
          {canWrite && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => navigate('/training-jobs/create')}
            >
              新建任务
            </Button>
          )}
        </Space>
      </div>
      <Table<TrainingJob>
        rowKey="id"
        columns={columns}
        dataSource={data?.items}
        loading={isLoading}
        scroll={{ x: 1160 }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100'],
          showTotal: (total) => `共 ${total} 条`,
        }}
        onChange={handleTableChange}
        locale={{
          emptyText: (
            <Empty description="还没有训练任务，选择数据集开始第一次训练">
              {canWrite && (
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => navigate('/training-jobs/create')}
                >
                  新建任务
                </Button>
              )}
            </Empty>
          ),
        }}
      />
    </div>
  )
}
