import { useState, useCallback } from 'react'
import { Button, DatePicker, Input, Select, Space, Table, Tag, Typography } from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import type { Dayjs } from 'dayjs'
import { getAuditLogs } from '@/services/audit'
import { formatDate } from '@/utils/format'
import type { AuditLog, AuditAction, ResourceType } from '@/types/audit'
import {
  ACTION_LABELS,
  ACTION_COLORS,
  ACTION_OPTIONS,
  RESOURCE_LABELS,
  RESOURCE_COLORS,
  RESOURCE_OPTIONS,
} from '@/utils/auditLabels'

function DetailPanel({ record }: { record: AuditLog }) {
  return (
    <div style={{ padding: '12px 0' }}>
      {record.detail && Object.keys(record.detail).length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <Typography.Text type="secondary">操作详情：</Typography.Text>
          <Typography.Paragraph copyable style={{ marginBottom: 4, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(record.detail, null, 2)}
          </Typography.Paragraph>
        </div>
      )}
      {record.userAgent && (
        <div style={{ marginBottom: 4 }}>
          <Typography.Text type="secondary">User-Agent：</Typography.Text>
          <Typography.Text style={{ fontSize: 12 }}>{record.userAgent}</Typography.Text>
        </div>
      )}
      {record.requestId && (
        <div>
          <Typography.Text type="secondary">Request ID：</Typography.Text>
          <Typography.Text code style={{ fontSize: 12 }}>
            {record.requestId}
          </Typography.Text>
        </div>
      )}
    </div>
  )
}

export default function AuditLogsPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const [timeRange, setTimeRange] = useState<[Dayjs, Dayjs]>()
  const [username, setUsername] = useState<string>()
  const [actionFilter, setActionFilter] = useState<AuditAction[]>()
  const [resourceTypeFilter, setResourceTypeFilter] = useState<ResourceType[]>()

  const [filters, setFilters] = useState<{
    startTime?: string
    endTime?: string
    username?: string
    action?: AuditAction[]
    resourceType?: ResourceType[]
  }>()

  const {
    data: res,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['audit-logs', page, pageSize, filters],
    queryFn: () =>
      getAuditLogs({
        page,
        pageSize,
        startTime: filters?.startTime,
        endTime: filters?.endTime,
        username: filters?.username,
        action: filters?.action?.length ? filters.action : undefined,
        resourceType: filters?.resourceType?.length ? filters.resourceType : undefined,
      }),
  })

  const handleSearch = () => {
    setFilters({
      startTime: timeRange?.[0]?.toISOString(),
      endTime: timeRange?.[1]?.toISOString(),
      username,
      action: actionFilter,
      resourceType: resourceTypeFilter,
    })
    setPage(1)
  }

  const handleReset = () => {
    setTimeRange(undefined)
    setUsername(undefined)
    setActionFilter(undefined)
    setResourceTypeFilter(undefined)
    setFilters(undefined)
    setPage(1)
  }

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const columns: ColumnsType<AuditLog> = [
    {
      title: '操作时间',
      dataIndex: 'createdAt',
      width: 180,
      render: (v: string) => formatDate(v),
    },
    {
      title: '操作人',
      dataIndex: 'username',
      width: 150,
      render: (_, record) =>
        record.username || (record.userId ? record.userId.substring(0, 8) + '...' : '系统'),
    },
    {
      title: '操作类型',
      dataIndex: 'action',
      width: 120,
      render: (_, record) => (
        <Tag color={ACTION_COLORS[record.action] || 'default'}>
          {ACTION_LABELS[record.action] || record.action}
        </Tag>
      ),
    },
    {
      title: '资源类型',
      dataIndex: 'resourceType',
      width: 120,
      render: (_, record) => (
        <Tag color={RESOURCE_COLORS[record.resourceType] || 'default'}>
          {RESOURCE_LABELS[record.resourceType] || record.resourceType}
        </Tag>
      ),
    },
    {
      title: '资源 ID',
      dataIndex: 'resourceId',
      width: 160,
      render: (_, record) =>
        record.resourceId ? (
          <Typography.Text copyable style={{ fontSize: 12 }}>
            {record.resourceId.length > 12
              ? record.resourceId.substring(0, 12) + '...'
              : record.resourceId}
          </Typography.Text>
        ) : (
          '-'
        ),
    },
    {
      title: 'IP 地址',
      dataIndex: 'ipAddress',
      width: 140,
    },
  ]

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <Space wrap>
          <DatePicker.RangePicker
            value={timeRange}
            onChange={(dates) => setTimeRange(dates as [Dayjs, Dayjs] | undefined)}
            style={{ width: 280 }}
          />
          <Input
            placeholder="搜索用户名"
            value={username}
            onChange={(e) => setUsername(e.target.value || undefined)}
            style={{ width: 160 }}
            prefix={<SearchOutlined />}
            onPressEnter={handleSearch}
          />
          <Select
            mode="multiple"
            placeholder="选择操作类型"
            value={actionFilter}
            onChange={(v) => setActionFilter(v as AuditAction[])}
            options={ACTION_OPTIONS}
            style={{ minWidth: 160 }}
            allowClear
          />
          <Select
            mode="multiple"
            placeholder="选择资源类型"
            value={resourceTypeFilter}
            onChange={(v) => setResourceTypeFilter(v as ResourceType[])}
            options={RESOURCE_OPTIONS}
            style={{ minWidth: 160 }}
            allowClear
          />
          <Button type="primary" onClick={handleSearch}>
            查询
          </Button>
          <Button onClick={handleReset}>重置</Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
            刷新
          </Button>
        </Space>
      </div>

      <Table<AuditLog>
        rowKey="id"
        columns={columns}
        dataSource={res?.data?.items}
        loading={isLoading}
        pagination={{
          current: page,
          pageSize,
          total: res?.data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
        }}
        onChange={handleTableChange}
        expandable={{
          expandedRowRender: (record) => <DetailPanel record={record} />,
        }}
        locale={{
          emptyText: (
            <div style={{ padding: '24px 0', textAlign: 'center' }}>
              <p style={{ color: 'var(--text-tertiary)', marginBottom: 16 }}>
                暂无审计日志，操作记录会自动出现在这里
              </p>
            </div>
          ),
        }}
      />
    </div>
  )
}
