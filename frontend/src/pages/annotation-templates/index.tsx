import { useState, useCallback } from 'react'
import { Button, Input, Popconfirm, Space, Table, Tag, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { listAnnotationTemplates, deleteAnnotationTemplate } from '@/services/annotation-templates'
import { useRbacStore } from '@/stores/rbacStore'
import { getMessageInstance } from '@/utils/messageHolder'
import type { AnnotationTemplate } from '@/types/annotation-template'

export default function AnnotationTemplatesPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [name, setName] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite =
    hasPermission('annotation_templates:write') || hasPermission('annotation_templates:manage')

  const { data, isLoading } = useQuery({
    queryKey: ['annotationTemplates', page, pageSize, name],
    queryFn: () => listAnnotationTemplates({ current: page, pageSize, name }),
  })

  const handleSearch = useCallback((value: string) => {
    setName(value || undefined)
    setPage(1)
  }, [])

  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteAnnotationTemplate(id)
        getMessageInstance()?.success('模板已删除')
        queryClient.invalidateQueries({ queryKey: ['annotationTemplates'] })
      } catch {
        // interceptor handles error toast
      }
    },
    [queryClient],
  )

  const columns: ColumnsType<AnnotationTemplate> = [
    {
      title: '模板名称',
      dataIndex: 'name',
      ellipsis: true,
    },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 200,
      render: (tags: string[]) => (
        <Space size={4} wrap>
          {tags.map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '分组',
      dataIndex: 'group',
      width: 120,
    },
    {
      title: '操作',
      key: 'actions',
      width: 80,
      render: (_: unknown, record: AnnotationTemplate) =>
        canWrite ? (
          <Popconfirm
            title="确认删除模板?"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="text" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        ) : null,
    },
  ]

  return (
    <div style={{ padding: 16 }}>
      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          justifyContent: 'space-between',
          gap: 12,
        }}
      >
        <Input.Search
          placeholder="按名称搜索"
          allowClear
          style={{ width: 280 }}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={handleSearch}
          prefix={<SearchOutlined />}
        />
        {canWrite && (
          <Button type="primary" icon={<PlusOutlined />}>
            新建模板
          </Button>
        )}
      </div>

      <Table<AnnotationTemplate>
        rowKey="id"
        columns={columns}
        dataSource={data?.items}
        loading={isLoading}
        locale={{ emptyText: <Typography.Text type="secondary">暂无模板</Typography.Text> }}
        pagination={{
          current: page,
          pageSize,
          total: data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
          },
        }}
      />
    </div>
  )
}
