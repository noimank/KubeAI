import { useState, useCallback, useMemo } from 'react'
import { Button, Empty, Input, Popconfirm, Segmented, Space, Table, Tag } from 'antd'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import type { TablePaginationConfig } from 'antd/es/table'
import { formatDate } from '@/utils/format'
import type {
  DevEnvironment,
  DevEnvironmentStatus,
  DatasetMountInfo,
} from '@/types/dev-environment'
import type { EnvironmentType } from '@/types/dev-environment-image'
import { ENVIRONMENT_TYPE_LABELS, ENVIRONMENT_TYPE_COLORS } from '@/types/dev-environment-image'

const STATUS_CONFIG: Record<DevEnvironmentStatus, { color: string; text: string }> = {
  pending: { color: 'warning', text: '待启动' },
  starting: { color: 'processing', text: '启动中' },
  running: { color: 'success', text: '运行中' },
  stopping: { color: 'processing', text: '停止中' },
  stopped: { color: 'default', text: '已停止' },
  failed: { color: 'error', text: '失败' },
}

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '待启动', value: 'pending' },
  { label: '启动中', value: 'starting' },
  { label: '运行中', value: 'running' },
  { label: '停止中', value: 'stopping' },
  { label: '已停止', value: 'stopped' },
  { label: '失败', value: 'failed' },
]

interface DevEnvListProps {
  data: { items: DevEnvironment[]; total: number } | undefined
  loading: boolean
  page: number
  pageSize: number
  statusFilter: string
  onPageChange: (page: number, pageSize: number) => void
  onStatusChange: (val: string) => void
  onSearch: (val: string) => void
  onOpenEnv: (envId: string) => void
  onTrain: (envId: string) => void
  onStop: (envId: string) => void
  onStart: (envId: string) => void
  onDelete: (envId: string) => void
  canWrite: boolean
  canManage: boolean
  currentUserId: string | undefined
  onCreateClick: () => void
}

export function DevEnvList({
  data,
  loading,
  page,
  pageSize,
  statusFilter,
  onPageChange,
  onStatusChange,
  onSearch,
  onOpenEnv,
  onTrain,
  onStop,
  onStart,
  onDelete,
  canWrite,
  canManage,
  currentUserId,
  onCreateClick,
}: DevEnvListProps) {
  const [searchText, setSearchText] = useState('')

  const handleTableChange = useCallback(
    (pagination: TablePaginationConfig) => {
      onPageChange(pagination.current || 1, pagination.pageSize || 20)
    },
    [onPageChange],
  )

  const columns = useMemo(
    () => [
      {
        title: '名称',
        dataIndex: 'name',
        width: 180,
        render: (name: string) => <span style={{ fontWeight: 500 }}>{name}</span>,
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 100,
        render: (val: DevEnvironmentStatus) => {
          const cfg = STATUS_CONFIG[val] || { color: 'default', text: val }
          return <Tag color={cfg.color}>{cfg.text}</Tag>
        },
      },
      {
        title: '类型',
        dataIndex: 'environmentType',
        width: 120,
        render: (type: string) => {
          if (!type) return <span style={{ color: '#999' }}>—</span>
          return (
            <Tag color={ENVIRONMENT_TYPE_COLORS[type as EnvironmentType]}>
              {ENVIRONMENT_TYPE_LABELS[type as EnvironmentType]}
            </Tag>
          )
        },
      },
      {
        title: '镜像',
        dataIndex: 'image',
        ellipsis: true,
      },
      {
        title: 'GPU',
        dataIndex: 'gpuCount',
        width: 80,
        render: (val: number) => (val > 0 ? `${val}` : '—'),
      },
      {
        title: 'CPU/内存',
        width: 120,
        render: (_: unknown, record: DevEnvironment) => `${record.cpu} 核 / ${record.memory}`,
      },
      {
        title: '挂载数据集',
        dataIndex: 'mountedDatasets',
        width: 160,
        render: (datasets: DatasetMountInfo[] | undefined) => {
          if (!datasets?.length) return <span style={{ color: '#999' }}>—</span>
          return (
            <Space size={4} wrap>
              {datasets.map((d) => (
                <Tag key={d.datasetId}>{d.datasetName}</Tag>
              ))}
            </Space>
          )
        },
      },
      {
        title: '活跃时间',
        dataIndex: 'lastActiveAt',
        width: 180,
        render: (val: string | undefined) => formatDate(val),
      },
      {
        title: '创建时间',
        dataIndex: 'createdAt',
        width: 180,
        render: (val: string) => formatDate(val),
      },
      {
        title: '操作',
        width: 320,
        render: (_: unknown, record: DevEnvironment) => (
          <Space size="small">
            {canWrite && record.status === 'running' && (
              <Button type="link" size="small" onClick={() => onTrain(record.id)}>
                提交训练
              </Button>
            )}
            {record.status === 'running' && (
              <Button type="link" size="small" onClick={() => onOpenEnv(record.id)}>
                打开环境
              </Button>
            )}
            {canWrite && ['running', 'starting'].includes(record.status) && (
              <Popconfirm
                title="确认停止该环境？"
                description="停止后可以重新启动"
                onConfirm={() => onStop(record.id)}
                okText="确认"
                cancelText="取消"
              >
                <Button type="link" size="small">
                  停止
                </Button>
              </Popconfirm>
            )}
            {canWrite && record.status === 'stopped' && (
              <Popconfirm
                title="确认启动该环境？"
                onConfirm={() => onStart(record.id)}
                okText="确认"
                cancelText="取消"
              >
                <Button type="link" size="small">
                  启动
                </Button>
              </Popconfirm>
            )}
            {record.status === 'failed' && (
              <span style={{ color: '#ff4d4f', fontSize: 12 }}>
                {record.errorMessage || '启动失败'}
              </span>
            )}
            {canWrite && (canManage || record.createdBy === currentUserId) && (
              <Popconfirm
                title="确认删除该环境？"
                description="删除后不可恢复，请谨慎操作。"
                onConfirm={() => onDelete(record.id)}
                okText="确认"
                cancelText="取消"
              >
                <Button type="link" size="small" danger>
                  删除
                </Button>
              </Popconfirm>
            )}
          </Space>
        ),
      },
    ],
    [canWrite, canManage, currentUserId, onOpenEnv, onTrain, onStop, onStart, onDelete],
  )

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Space>
          <Segmented
            options={STATUS_TABS}
            value={statusFilter}
            onChange={(val) => onStatusChange(val as string)}
          />
          <Input.Search
            placeholder="搜索环境名称"
            allowClear
            style={{ width: 280 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={onSearch}
            prefix={<SearchOutlined />}
          />
        </Space>
        <Space>
          {canWrite && (
            <Button type="primary" icon={<PlusOutlined />} onClick={onCreateClick}>
              创建开发环境
            </Button>
          )}
        </Space>
      </div>

      <Table<DevEnvironment>
        rowKey="id"
        columns={columns}
        dataSource={data?.items}
        loading={loading}
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
            <Empty description="还没有开发环境，创建一个开始编码">
              {canWrite && (
                <Button type="primary" icon={<PlusOutlined />} onClick={onCreateClick}>
                  创建开发环境
                </Button>
              )}
            </Empty>
          ),
        }}
      />
    </>
  )
}
