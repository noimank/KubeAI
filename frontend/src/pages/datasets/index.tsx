import { useState, useCallback } from 'react'
import { Button, DatePicker, Form, Input, Modal, Popconfirm, Space, Table, message } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { createDataset, deleteDataset, getDatasets } from '@/services/datasets'
import { formatFileSize } from '@/utils/format'
import type { Dataset } from '@/types/dataset'

export default function DatasetsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')
  const [dateRange, setDateRange] = useState<[string, string] | undefined>()

  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDisplayName, setNewDisplayName] = useState('')
  const [newDesc, setNewDesc] = useState('')

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('datasets:write')
  const canManage = hasPermission('datasets:manage')

  const { data, isLoading } = useQuery({
    queryKey: ['datasets', page, pageSize, keyword, dateRange],
    queryFn: () =>
      getDatasets({
        current: page,
        pageSize,
        keyword,
        startDate: dateRange?.[0],
        endDate: dateRange?.[1],
      }),
  })

  const createMutation = useMutation({
    mutationFn: (values: { name: string; displayName?: string; description?: string }) =>
      createDataset(values),
    onSuccess: (detail) => {
      getMessageInstance()?.success('数据集创建成功')
      setCreateModalOpen(false)
      setNewName('')
      setNewDesc('')
      navigate(`/datasets/${detail.id}`)
    },
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleDateRangeChange = useCallback((_: unknown, dateStrings: [string, string]) => {
    if (dateStrings[0] && dateStrings[1]) {
      setDateRange([dateStrings[0], dateStrings[1]])
    } else {
      setDateRange(undefined)
    }
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
      queryClient.invalidateQueries({ queryKey: ['datasets'] })
    } catch {
      // interceptor handles error toast
    }
  }

  const columns: ColumnsType<Dataset> = [
    {
      title: '名称',
      dataIndex: 'displayName',
      render: (displayName: string | undefined, record: Dataset) => displayName || record.name,
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

  const handleCreateOk = () => {
    const trimmed = newName.trim()
    if (!trimmed) return
    if (trimmed.length > 200) return
    if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(trimmed)) {
      message.warning('数据集名称仅支持小写字母、数字和中划线，且以字母或数字开头')
      return
    }
    createMutation.mutate({
      name: trimmed,
      displayName: newDisplayName.trim() || undefined,
      description: newDesc.trim() || undefined,
    })
  }

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Space>
          <Input.Search
            placeholder="搜索数据集名称"
            allowClear
            style={{ width: 280 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
            prefix={<SearchOutlined />}
          />
          <DatePicker.RangePicker
            placeholder={['开始日期', '结束日期']}
            onChange={handleDateRangeChange}
            style={{ width: 260 }}
          />
        </Space>
        {canWrite && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            创建数据集
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
              {canWrite && (
                <Button
                  type="primary"
                  icon={<PlusOutlined />}
                  onClick={() => setCreateModalOpen(true)}
                >
                  创建数据集
                </Button>
              )}
            </div>
          ),
        }}
      />

      <Modal
        title="创建数据集"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false)
          setNewName('')
          setNewDisplayName('')
          setNewDesc('')
        }}
        onOk={handleCreateOk}
        confirmLoading={createMutation.isPending}
        okText="创建"
        cancelText="取消"
        destroyOnHidden
        okButtonProps={{ disabled: !newName.trim() || newName.trim().length > 200 }}
      >
        <Form layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item label="数据集名称" required>
            <Input
              placeholder="仅支持小写字母、数字和中划线"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              maxLength={200}
              showCount
            />
          </Form.Item>
          <Form.Item label="显示名称">
            <Input
              placeholder="可选，支持中文"
              value={newDisplayName}
              onChange={(e) => setNewDisplayName(e.target.value)}
              maxLength={200}
              showCount
            />
          </Form.Item>
          <Form.Item label="描述">
            <Input.TextArea
              placeholder="可选"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              rows={3}
              maxLength={500}
              showCount
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
