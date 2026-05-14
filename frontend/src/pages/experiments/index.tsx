import { useState, useCallback } from 'react'
import {
  Alert,
  Button,
  DatePicker,
  Empty,
  Input,
  Segmented,
  Select,
  Skeleton,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import { Link } from 'react-router-dom'
import { SearchOutlined, SwapOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { getExperiments } from '@/services/experiments'
import { getDatasets } from '@/services/datasets'
import { getImages } from '@/services/images'
import type { Experiment } from '@/types/experiment'
import ExperimentCompareDrawer from './components/ExperimentCompareDrawer'

const { RangePicker } = DatePicker

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
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [compareOpen, setCompareOpen] = useState(false)
  const [sortField, setSortField] = useState<string | undefined>()
  const [sortOrder, setSortOrder] = useState<string | undefined>()

  // Advanced filters
  const [dateRange, setDateRange] = useState<[string, string] | undefined>()
  const [datasetId, setDatasetId] = useState<string | undefined>()
  const [imageId, setImageId] = useState<string | undefined>()

  const { data, isLoading, isPending, isFetching } = useQuery({
    queryKey: [
      'experiments',
      page,
      pageSize,
      statusFilter,
      keyword,
      sortField,
      sortOrder,
      dateRange,
      datasetId,
      imageId,
    ],
    queryFn: () =>
      getExperiments({
        current: page,
        pageSize,
        status: statusFilter || undefined,
        trainingJobName: keyword,
        sortBy: sortField,
        sortOrder,
        startDate: dateRange?.[0],
        endDate: dateRange?.[1],
        datasetId,
        imageId,
      }),
  })

  // Dataset options for filter (cached 5 minutes)
  const { data: datasetsData } = useQuery({
    queryKey: ['datasets-options'],
    queryFn: () => getDatasets({ current: 1, pageSize: 100 }),
    staleTime: 5 * 60 * 1000,
  })

  // Image options for filter (cached 5 minutes)
  const { data: imagesData } = useQuery({
    queryKey: ['images-options'],
    queryFn: () => getImages({ current: 1, pageSize: 100 }),
    staleTime: 5 * 60 * 1000,
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback(
    (pagination: TablePaginationConfig, _filters: Record<string, unknown>, sorter: unknown) => {
      setPage(pagination.current || 1)
      setPageSize(pagination.pageSize || 20)
      // Handle column sort
      const s = sorter as { field?: string; order?: string; columnKey?: string } | unknown[]
      if (s && !Array.isArray(s)) {
        const sorted = s as { field?: string; order?: string; columnKey?: string }
        if (sorted.order) {
          setSortField(sorted.field || sorted.columnKey)
          setSortOrder(sorted.order === 'ascend' ? 'asc' : 'desc')
        } else {
          setSortField(undefined)
          setSortOrder(undefined)
        }
      }
    },
    [],
  )

  const handleCompare = useCallback(() => {
    if (selectedRowKeys.length >= 2) {
      setCompareOpen(true)
    }
  }, [selectedRowKeys])

  const columns: ColumnsType<Experiment> = [
    {
      title: '训练任务',
      dataIndex: 'trainingJobName',
      ellipsis: true,
      render: (name: string, record: Experiment) =>
        name ? <Link to={`/training-jobs/${record.trainingJobId}`}>{name}</Link> : '—',
    },
    {
      title: '实验名称',
      key: 'experimentName',
      width: 180,
      render: (_: unknown, record: Experiment) => (
        <Link to={`/experiments/${record.id}`}>
          {record.trainingJobName || record.id.slice(0, 8)}
        </Link>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      sorter: true,
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
      sorter: true,
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
      sorter: true,
    },
  ]

  const emptyContent = (
    <Empty
      description="还没有实验记录，提交训练任务后实验会自动追踪到这里"
      image={Empty.PRESENTED_IMAGE_SIMPLE}
    >
      <Link to="/training-jobs/create">
        <Button type="primary">新建训练任务</Button>
      </Link>
    </Empty>
  )

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
        <Space wrap>
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
          <RangePicker
            placeholder={['开始日期', '结束日期']}
            onChange={(_, dateStrings) => {
              if (dateStrings[0] && dateStrings[1]) {
                setDateRange([dateStrings[0], dateStrings[1]])
              } else {
                setDateRange(undefined)
              }
              setPage(1)
            }}
          />
          <Select
            placeholder="关联数据集"
            allowClear
            style={{ width: 180 }}
            value={datasetId}
            onChange={(val) => {
              setDatasetId(val)
              setPage(1)
            }}
            options={datasetsData?.items?.map((d) => ({ label: d.name, value: d.id }))}
          />
          <Select
            placeholder="关联镜像"
            allowClear
            style={{ width: 180 }}
            value={imageId}
            onChange={(val) => {
              setImageId(val)
              setPage(1)
            }}
            options={imagesData?.items?.map((img) => ({ label: img.name, value: img.id }))}
          />
        </Space>
      </div>
      {isPending ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : (
        <Table<Experiment>
          rowKey="id"
          columns={columns}
          dataSource={data?.items}
          loading={isFetching}
          rowSelection={{
            selectedRowKeys,
            onChange: (keys) => {
              const selected = keys as string[]
              if (selected.length <= 5) {
                setSelectedRowKeys(selected)
              }
            },
            selections: false,
            getCheckboxProps: (record) => ({
              disabled: selectedRowKeys.length >= 5 && !selectedRowKeys.includes(record.id),
            }),
          }}
          pagination={{
            current: page,
            pageSize,
            total: data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (total) => `共 ${total} 条`,
          }}
          onChange={handleTableChange}
          locale={{ emptyText: emptyContent }}
        />
      )}
      {/* Floating action bar for comparison */}
      {selectedRowKeys.length > 0 && (
        <div
          style={{
            position: 'fixed',
            bottom: 24,
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 100,
            background: 'var(--ant-color-bg-container)',
            border: '1px solid var(--ant-color-border)',
            borderRadius: 8,
            padding: '8px 16px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span>已选 {selectedRowKeys.length} 个实验（最多 5 个）</span>
          <Button
            type="primary"
            icon={<SwapOutlined />}
            disabled={selectedRowKeys.length < 2}
            onClick={handleCompare}
          >
            对比
          </Button>
          <Button onClick={() => setSelectedRowKeys([])}>取消选择</Button>
        </div>
      )}
      <ExperimentCompareDrawer
        open={compareOpen}
        experimentIds={selectedRowKeys}
        onClose={() => setCompareOpen(false)}
      />
    </div>
  )
}
