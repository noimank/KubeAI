import { useState, useCallback } from 'react'
import { Alert, Empty, Input, Segmented, Space, Table, Tag, Tooltip } from 'antd'
import { Link } from 'react-router-dom'
import { SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { getExperiments } from '@/services/experiments'
import type { Experiment } from '@/types/experiment'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  active: { color: 'processing', text: '运行中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '已失败' },
}

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '运行中', value: 'active' },
  { label: '已完成', value: 'completed' },
  { label: '已失败', value: 'failed' },
]

function formatHyperparams(params: Record<string, string> | null): string {
  if (!params) return '—'
  const entries = Object.entries(params).slice(0, 5)
  return entries.map(([k, v]) => `${k}=${v}`).join(', ')
}

function formatMetrics(metrics: Array<{ key: string; value: number }> | null): string {
  if (!metrics || metrics.length === 0) return '—'
  return metrics
    .map((m) => `${m.key}: ${typeof m.value === 'number' ? m.value.toFixed(4) : m.value}`)
    .join(', ')
}

export default function ExperimentsPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState('')
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['experiments', page, pageSize, statusFilter, keyword],
    queryFn: () =>
      getExperiments({
        current: page,
        pageSize,
        status: statusFilter || undefined,
        trainingJobName: keyword,
      }),
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const columns: ColumnsType<Experiment> = [
    {
      title: '训练任务',
      dataIndex: 'trainingJobName',
      ellipsis: true,
      render: (name: string, record: Experiment) =>
        name ? <Link to={`/training-jobs/${record.trainingJobId}`}>{name}</Link> : '—',
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (val: string) => {
        const cfg = STATUS_CONFIG[val] || { color: 'default', text: val }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '超参数',
      key: 'hyperparameters',
      width: 200,
      ellipsis: true,
      render: (_: unknown, record: Experiment) => {
        if (!record.hyperparameters || Object.keys(record.hyperparameters).length === 0) return '—'
        const summary = formatHyperparams(record.hyperparameters)
        const full = Object.entries(record.hyperparameters)
          .map(([k, v]) => `${k}=${v}`)
          .join('\n')
        return (
          <Tooltip title={<pre style={{ margin: 0, fontSize: 12 }}>{full}</pre>}>
            <span>{summary}</span>
          </Tooltip>
        )
      },
    },
    {
      title: '关键指标',
      key: 'metrics',
      width: 200,
      ellipsis: true,
      render: (_: unknown, record: Experiment) => {
        if (!record.metrics || record.metrics.length === 0) return '—'
        return <span>{formatMetrics(record.metrics)}</span>
      },
    },
    {
      title: '数据集版本',
      dataIndex: 'datasetVersion',
      width: 120,
      render: (val: string | null) => val || '—',
    },
    {
      title: '镜像',
      dataIndex: 'imageName',
      width: 150,
      ellipsis: true,
      render: (val: string | null) => val || '—',
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      {!data && !isLoading && (
        <Alert
          message="MLflow 实验追踪未启用，请联系管理员配置"
          type="info"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}
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
            placeholder="搜索训练任务名称"
            allowClear
            style={{ width: 280 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
            prefix={<SearchOutlined />}
          />
        </Space>
      </div>
      <Table<Experiment>
        rowKey="id"
        columns={columns}
        dataSource={data?.items}
        loading={isLoading}
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
          emptyText: <Empty description="还没有实验记录，提交训练任务后实验数据会自动记录到这里" />,
        }}
      />
    </div>
  )
}
