import { useState, useCallback } from 'react'
import { Button, Empty, Input, Popconfirm, Segmented, Space, Table, Tag, Typography } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import {
  getInferenceServices,
  stopInferenceService,
  deleteInferenceService,
} from '@/services/inference'
import type { InferenceService, InferenceServiceStatus } from '@/types/inference'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'warning', text: '等待中' },
  deploying: { color: 'processing', text: '部署中' },
  running: { color: 'success', text: '运行中' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

const CANARY_STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  deploying: { color: 'processing', text: '金丝雀部署中' },
  running: { color: 'success', text: '金丝雀运行' },
  failed: { color: 'error', text: '金丝雀失败' },
}

export default function InferencePage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [keyword, setKeyword] = useState<string | undefined>(undefined)
  const [searchText, setSearchText] = useState('')

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('inference_services:write')
  const canManage = hasPermission('inference_services:manage')

  const { data, isLoading } = useQuery({
    queryKey: ['inferenceServices', page, pageSize, statusFilter, keyword],
    queryFn: () =>
      getInferenceServices({
        current: page,
        pageSize,
        status: statusFilter || undefined,
        name: keyword,
      }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const hasActive = items.some((s) => ['pending', 'deploying'].includes(s.status))
      return hasActive ? 5000 : false
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopInferenceService,
    onSuccess: () => {
      getMessageInstance()?.success('推理服务已停止')
      queryClient.invalidateQueries({ queryKey: ['inferenceServices'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteInferenceService,
    onSuccess: () => {
      getMessageInstance()?.success('推理服务已删除')
      queryClient.invalidateQueries({ queryKey: ['inferenceServices'] })
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

  const columns: ColumnsType<InferenceService> = [
    {
      title: '名称',
      dataIndex: 'name',
      ellipsis: true,
      render: (name: string, record: InferenceService) => (
        <Link to={`/inference/${record.id}`}>{name}</Link>
      ),
    },
    {
      title: '模型版本',
      width: 150,
      render: (_: unknown, record: InferenceService) => {
        if (!record.modelVersion) return <Typography.Text type="secondary">—</Typography.Text>
        return (
          <Typography.Text>
            {record.modelVersion.versionNumber
              ? `v${record.modelVersion.versionNumber}`
              : record.modelVersion.id.slice(0, 8)}
          </Typography.Text>
        )
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (val: InferenceServiceStatus) => {
        const cfg = STATUS_CONFIG[val] || { color: 'default', text: val }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: 'GPU',
      dataIndex: 'gpuCount',
      width: 80,
      render: (val: number) => (val > 0 ? `${val} 张` : '—'),
    },
    {
      title: '副本数',
      dataIndex: 'replicas',
      width: 80,
    },
    {
      title: '金丝雀',
      width: 120,
      render: (_: unknown, record: InferenceService) => {
        if (record.canaryStatus === 'none' || !record.canaryStatus)
          return <Typography.Text type="secondary">—</Typography.Text>
        const cfg = CANARY_STATUS_CONFIG[record.canaryStatus] || {
          color: 'default',
          text: record.canaryStatus,
        }
        return (
          <Space size={4}>
            <Tag color={cfg.color} style={{ fontSize: 11 }}>
              {cfg.text}
            </Tag>
            {record.canaryTrafficPercent != null && (
              <span style={{ fontSize: 11, color: '#666' }}>{record.canaryTrafficPercent}%</span>
            )}
          </Space>
        )
      },
    },
    {
      title: '推理端点',
      dataIndex: 'proxyEndpoint',
      width: 260,
      ellipsis: true,
      render: (url: string | undefined) =>
        url ? (
          <Space size={4}>
            <Typography.Text
              copyable={{ text: url, tooltips: ['复制', '已复制'] }}
              style={{ maxWidth: 220 }}
              ellipsis
            >
              {url}
            </Typography.Text>
          </Space>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        ),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
    },
    {
      title: '操作',
      width: 160,
      render: (_: unknown, record: InferenceService) => (
        <Space size="small">
          <Link to={`/inference/${record.id}`}>
            <Button type="link" size="small">
              详情
            </Button>
          </Link>
          {canWrite && ['running', 'deploying', 'pending'].includes(record.status) && (
            <Popconfirm
              title="确认停止该服务？"
              description="停止后副本数将设为 0，配置保留"
              onConfirm={() => stopMutation.mutate(record.id)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>
                停止
              </Button>
            </Popconfirm>
          )}
          {canManage && (
            <Popconfirm
              title="确认删除该服务？"
              description="删除后不可恢复"
              onConfirm={() => deleteMutation.mutate(record.id)}
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
  ]

  const statusTabs = [
    { label: '全部', value: '' },
    { label: '部署中', value: 'deploying' },
    { label: '运行中', value: 'running' },
    { label: '已失败', value: 'failed' },
    { label: '已停止', value: 'stopped' },
  ]

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Space>
          <Segmented
            options={statusTabs}
            value={statusFilter}
            onChange={(val) => {
              setStatusFilter(val as string)
              setPage(1)
            }}
          />
          <Input.Search
            placeholder="搜索服务名称"
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
            onClick={() => queryClient.invalidateQueries({ queryKey: ['inferenceServices'] })}
          >
            刷新
          </Button>
          {canWrite && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => navigate('/inference/create')}
            >
              部署推理服务
            </Button>
          )}
        </Space>
      </div>
      <Table<InferenceService>
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
          emptyText: (
            <Empty description="还没有推理服务，从模型仓库选择一个模型部署">
              {canWrite && (
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => navigate('/inference/create')}
                >
                  部署推理服务
                </Button>
              )}
            </Empty>
          ),
        }}
      />
    </div>
  )
}
