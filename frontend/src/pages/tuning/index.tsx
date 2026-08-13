import { useCallback, useState } from 'react'
import { Button, Empty, Input, Popconfirm, Progress, Segmented, Space, Table, Tag } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import {
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { formatDate } from '@/utils/format'
import { useRbacStore } from '@/stores/rbacStore'
import {
  deleteTuningStudy,
  getTuningStudies,
  pauseTuningStudy,
  resumeTuningStudy,
  stopTuningStudy,
} from '@/services/tuning'
import type { TuningStudy, TuningStudyStatus } from '@/types/tuning'

const STATUS_CONFIG: Record<TuningStudyStatus, { color: string; text: string }> = {
  running: { color: 'processing', text: '调优中' },
  completed: { color: 'success', text: '已完成' },
  stopped: { color: 'default', text: '已停止' },
  failed: { color: 'error', text: '已失败' },
  paused: { color: 'warning', text: '已暂停' },
}

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '调优中', value: 'running' },
  { label: '已完成', value: 'completed' },
  { label: '已失败', value: 'failed' },
  { label: '已停止', value: 'stopped' },
  { label: '已暂停', value: 'paused' },
]

function formatBest(value?: number): string {
  return value === undefined || value === null ? '—' : String(value)
}

export default function TuningPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState('')
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('tuning:write')
  const canManage = hasPermission('tuning:manage')

  const { data, isLoading } = useQuery({
    queryKey: ['tuningStudies', page, pageSize, statusFilter, keyword],
    queryFn: () =>
      getTuningStudies({
        current: page,
        pageSize,
        status: statusFilter || undefined,
        name: keyword,
      }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const hasActive = items.some((s) => s.status === 'running')
      return hasActive ? 5000 : false
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopTuningStudy,
    onSuccess: () => {
      getMessageInstance()?.success('调优任务已停止')
      queryClient.invalidateQueries({ queryKey: ['tuningStudies'] })
    },
  })

  const pauseMutation = useMutation({
    mutationFn: pauseTuningStudy,
    onSuccess: () => {
      getMessageInstance()?.success('调优任务已暂停')
      queryClient.invalidateQueries({ queryKey: ['tuningStudies'] })
    },
  })

  const resumeMutation = useMutation({
    mutationFn: resumeTuningStudy,
    onSuccess: () => {
      getMessageInstance()?.success('调优任务已恢复')
      queryClient.invalidateQueries({ queryKey: ['tuningStudies'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteTuningStudy,
    onSuccess: () => {
      getMessageInstance()?.success('调优任务已删除')
      queryClient.invalidateQueries({ queryKey: ['tuningStudies'] })
    },
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = (pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }

  const columns: ColumnsType<TuningStudy> = [
    {
      title: '名称',
      dataIndex: 'name',
      width: 220,
      ellipsis: true,
      fixed: 'left',
      render: (name: string, record: TuningStudy) => (
        <Link to={`/tuning/${record.id}`}>{name}</Link>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (val: TuningStudyStatus) => {
        const cfg = STATUS_CONFIG[val] ?? { color: 'default', text: val }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '进度',
      key: 'progress',
      width: 180,
      render: (_, record: TuningStudy) => {
        const percent =
          record.nTrials > 0 ? Math.round((record.finalizedCount / record.nTrials) * 100) : 0
        return (
          <Progress
            percent={percent}
            size="small"
            format={() => `${record.finalizedCount}/${record.nTrials}`}
          />
        )
      },
    },
    {
      title: '目标指标',
      dataIndex: 'metricName',
      width: 140,
      render: (val: string, record: TuningStudy) => (
        <Space size={4}>
          <Tag color={record.direction === 'minimize' ? 'blue' : 'orange'}>
            {record.direction === 'minimize' ? '最小化' : '最大化'}
          </Tag>
          <span>{val}</span>
        </Space>
      ),
    },
    {
      title: '最优值',
      dataIndex: 'bestValue',
      width: 120,
      render: (val: number | undefined) => formatBest(val),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 160,
      render: (val: string) => formatDate(val),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_, record: TuningStudy) => (
        <Space>
          <Link to={`/tuning/${record.id}`}>详情</Link>
          {record.status === 'running' && canWrite && (
            <Popconfirm
              title="确认暂停该调优任务？运行中的 trial 会被停止并释放资源。"
              onConfirm={() => pauseMutation.mutate(record.id)}
            >
              <Button type="link" size="small">
                暂停
              </Button>
            </Popconfirm>
          )}
          {record.status === 'paused' && canWrite && (
            <Popconfirm
              title="确认恢复该调优任务？将从此前进度继续补发 trial。"
              onConfirm={() => resumeMutation.mutate(record.id)}
            >
              <Button type="link" size="small">
                恢复
              </Button>
            </Popconfirm>
          )}
          {record.status === 'running' && canWrite && (
            <Popconfirm
              title="确认停止该调优任务？"
              onConfirm={() => stopMutation.mutate(record.id)}
            >
              <Button type="link" size="small">
                停止
              </Button>
            </Popconfirm>
          )}
          {canManage && (
            <Popconfirm
              title="确认删除该调优任务？其 trial 训练任务也会一并清理。"
              onConfirm={() => deleteMutation.mutate(record.id)}
            >
              <Button type="link" size="small" danger>
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
            placeholder="搜索调优任务名称"
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
            onClick={() => queryClient.invalidateQueries({ queryKey: ['tuningStudies'] })}
          >
            刷新
          </Button>
          {canWrite && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => navigate('/tuning/create')}
            >
              新建调优任务
            </Button>
          )}
        </Space>
      </div>
      <Table<TuningStudy>
        rowKey="id"
        loading={isLoading}
        columns={columns}
        dataSource={data?.items ?? []}
        scroll={{ x: 1120 }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100'],
          showTotal: (t) => `共 ${t} 项`,
        }}
        onChange={handleTableChange}
        locale={{
          emptyText: (
            <Empty
              image={<ThunderboltOutlined style={{ fontSize: 40, color: '#ccc' }} />}
              description="还没有调优任务，定义搜索空间开始自动寻优"
            >
              {canWrite && (
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => navigate('/tuning/create')}
                >
                  新建调优任务
                </Button>
              )}
            </Empty>
          ),
        }}
      />
    </div>
  )
}
