import { useState, useCallback } from 'react'
import { Button, Empty, Input, Skeleton, Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import { SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { getModels } from '@/services/models'
import { formatDate } from '@/utils/format'
import type { RegisteredModel } from '@/types/model'

function formatHyperparamsShort(params?: Record<string, string> | null): string {
  if (!params || Object.keys(params).length === 0) return '-'
  const entries = Object.entries(params).slice(0, 3)
  const text = entries.map(([k, v]) => `${k}=${v}`).join(', ')
  const remaining = Object.keys(params).length - 3
  return remaining > 0 ? `${text}, +${remaining} 项` : text
}

export default function ModelsPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const { data, isPending, isFetching } = useQuery({
    queryKey: ['models', page, pageSize, keyword],
    queryFn: () => getModels({ current: page, pageSize, search: keyword }),
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const columns: ColumnsType<RegisteredModel> = [
    {
      title: '名称',
      dataIndex: 'name',
      ellipsis: true,
      render: (name: string, record: RegisteredModel) => (
        <Link to={`/models/${record.id}`}>{name}</Link>
      ),
    },
    {
      title: '版本数',
      dataIndex: 'versionCount',
      width: 80,
      render: (count: number) => <Tag>{count}</Tag>,
    },
    {
      title: '最新指标',
      width: 200,
      render: (_: unknown, record: RegisteredModel) =>
        formatHyperparamsShort(record.latestVersion?.hyperparameters),
    },
    {
      title: '最新版本时间',
      width: 180,
      render: (_: unknown, record: RegisteredModel) =>
        record.latestVersion?.createdAt ? formatDate(record.latestVersion.createdAt) : '-',
    },
    {
      title: '来源训练任务',
      width: 160,
      render: (_: unknown, record: RegisteredModel) => record.latestVersion?.trainingJobName || '-',
    },
    {
      title: '操作',
      width: 80,
      render: (_: unknown, record: RegisteredModel) => (
        <Link to={`/models/${record.id}`}>
          <Button type="link" size="small">
            查看详情
          </Button>
        </Link>
      ),
    },
  ]

  const emptyContent = (
    <Empty
      description="模型仓库为空，训练完成后模型会自动归档到这里"
      image={Empty.PRESENTED_IMAGE_SIMPLE}
    >
      <Link to="/training-jobs/create">
        <Button type="primary">新建训练任务</Button>
      </Link>
    </Empty>
  )

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Input.Search
          placeholder="搜索模型名称"
          allowClear
          style={{ width: 280 }}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={handleSearch}
          prefix={<SearchOutlined />}
        />
      </div>
      {isPending ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : (
        <Table<RegisteredModel>
          rowKey="id"
          columns={columns}
          dataSource={data?.items}
          loading={isFetching}
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
    </div>
  )
}
