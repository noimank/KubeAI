import { useState, useCallback } from 'react'
import { Button, Input, Popconfirm, Space, Table } from 'antd'
import { Link } from 'react-router-dom'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { deleteDataset, getDatasets } from '@/services/datasets'
import { formatFileSize } from '@/utils/format'
import type { Dataset } from '@/types/dataset'

export default function DatasetsPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canManage = hasPermission('datasets:manage')

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['datasets', page, pageSize, keyword],
    queryFn: () => getDatasets({ current: page, pageSize, keyword }),
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const handleDelete = async (id: string) => {
    try {
      await deleteDataset(id)
      getMessageInstance()?.success('数据集删除成功')
      refetch()
    } catch {
      // interceptor handles error toast
    }
  }

  const columns: ColumnsType<Dataset> = [
    {
      title: '名称',
      dataIndex: 'name',
      ellipsis: true,
    },
    {
      title: '版本数',
      dataIndex: 'versionCount',
      width: 80,
    },
    {
      title: '文件数',
      dataIndex: 'totalFileCount',
      width: 80,
    },
    {
      title: '总大小',
      dataIndex: 'totalSizeBytes',
      width: 120,
      render: (_, record) => formatFileSize(record.totalSizeBytes),
    },
    {
      title: '创建人',
      dataIndex: 'createdByName',
      width: 120,
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
    },
    {
      title: '更新时间',
      dataIndex: 'updatedAt',
      width: 180,
    },
    {
      title: '操作',
      width: 120,
      render: (_, record) => (
        <Space size="small">
          <Link to={`/datasets/${record.id}`}>
            <Button type="link" size="small">
              详情
            </Button>
          </Link>
          {canManage && (
            <Popconfirm
              title="确认删除该数据集？"
              description="删除后，所有版本和文件将被永久清除，此操作不可恢复。"
              onConfirm={() => handleDelete(record.id)}
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

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Input.Search
          placeholder="搜索数据集名称"
          allowClear
          style={{ width: 320 }}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={handleSearch}
          prefix={<SearchOutlined />}
        />
        {canManage && (
          <Button type="primary" icon={<PlusOutlined />}>
            上传数据集
          </Button>
        )}
      </div>
      <Table<Dataset>
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
            <div style={{ padding: '24px 0', textAlign: 'center' }}>
              <p style={{ color: 'var(--text-tertiary)', marginBottom: 16 }}>
                还没有数据集，上传你的第一批数据开始吧
              </p>
              <Button type="primary" icon={<PlusOutlined />}>
                上传数据集
              </Button>
            </div>
          ),
        }}
      />
    </div>
  )
}
