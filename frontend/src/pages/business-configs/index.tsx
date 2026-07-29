import { useState, useCallback } from 'react'
import { Button, Form, Input, Modal, Popconfirm, Space, Table } from 'antd'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import {
  createBusinessConfig,
  deleteBusinessConfig,
  getBusinessConfigs,
  updateBusinessConfig,
} from '@/services/business-configs'
import { formatDate } from '@/utils/format'
import EnvVarEditor from '@/components/EnvVarEditor'
import type { BusinessConfig } from '@/types/business-config'

export default function BusinessConfigsPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [form] = Form.useForm()

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('business_configs:write')
  const canManage = hasPermission('business_configs:manage')

  const { data, isLoading } = useQuery({
    queryKey: ['business-configs', page, pageSize, keyword],
    queryFn: () => getBusinessConfigs({ current: page, pageSize, search: keyword }),
  })

  const createMutation = useMutation({
    mutationFn: (values: { name: string; description?: string; envVars: Record<string, string> }) =>
      createBusinessConfig(values),
    onSuccess: () => {
      getMessageInstance()?.success('业务配置创建成功')
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['business-configs'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: Record<string, unknown> }) =>
      updateBusinessConfig(id, data),
    onSuccess: () => {
      getMessageInstance()?.success('业务配置更新成功')
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['business-configs'] })
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

  const handleDelete = async (id: string) => {
    try {
      await deleteBusinessConfig(id)
      getMessageInstance()?.success('业务配置已删除')
      queryClient.invalidateQueries({ queryKey: ['business-configs'] })
    } catch {
      // interceptor handles error toast
    }
  }

  const openCreateModal = () => {
    setEditingId(null)
    form.resetFields()
    form.setFieldsValue({ envVars: [] })
    setModalOpen(true)
  }

  const openEditModal = (record: BusinessConfig) => {
    setEditingId(record.id)
    form.setFieldsValue({
      name: record.name,
      description: record.description,
      envVars: Object.entries(record.envVars).map(([key, value]) => ({ key, value })),
    })
    setModalOpen(true)
  }

  const closeModal = () => {
    setModalOpen(false)
    setEditingId(null)
    form.resetFields()
  }

  const handleFormFinish = () => {
    form
      .validateFields()
      .then((values) => {
        const envVars = (values.envVars || []).reduce(
          (acc: Record<string, string>, item: { key?: string; value?: string }) => {
            const key = item.key?.trim()
            if (key) acc[key] = item.value ?? ''
            return acc
          },
          {},
        )
        const payload = {
          name: values.name.trim(),
          description: values.description?.trim() || undefined,
          envVars,
        }
        if (editingId) {
          updateMutation.mutate({ id: editingId, data: payload })
        } else {
          createMutation.mutate(payload)
        }
      })
      .catch(() => {})
  }

  const envVarCount = (envVars?: Record<string, string>) =>
    envVars ? Object.keys(envVars).length : 0

  const columns: ColumnsType<BusinessConfig> = [
    {
      title: '名称',
      dataIndex: 'name',
      ellipsis: true,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      render: (v: string | undefined) => v || '-',
    },
    {
      title: '环境变量数',
      dataIndex: 'envVars',
      width: 120,
      render: (_, record) => envVarCount(record.envVars),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
      render: (v: string) => formatDate(v),
    },
    {
      title: '操作',
      width: 160,
      render: (_, record) => (
        <Space size="small">
          {canWrite && (
            <Button type="link" size="small" onClick={() => openEditModal(record)}>
              编辑
            </Button>
          )}
          {canManage && (
            <Popconfirm
              title="确认删除该业务配置？"
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
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Input.Search
          placeholder="搜索配置名称或描述"
          allowClear
          style={{ width: 320 }}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={handleSearch}
          prefix={<SearchOutlined />}
        />
        {canWrite && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            创建业务配置
          </Button>
        )}
      </div>
      <Table<BusinessConfig>
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
                还没有业务配置，创建你的第一个环境变量预设
              </p>
              {canWrite && (
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
                  创建业务配置
                </Button>
              )}
            </div>
          ),
        }}
      />

      <Modal
        title={editingId ? '编辑业务配置' : '创建业务配置'}
        open={modalOpen}
        onCancel={closeModal}
        onOk={handleFormFinish}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        okText={editingId ? '保存' : '创建'}
        cancelText="取消"
        destroyOnHidden
        width={640}
      >
        <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
          <Form.Item
            label="配置名称"
            name="name"
            rules={[{ required: true, message: '请输入配置名称' }]}
          >
            <Input placeholder="例如：生产环境、测试环境" maxLength={100} showCount />
          </Form.Item>
          <Form.Item label="描述" name="description">
            <Input.TextArea
              placeholder="可选，描述该配置的用途"
              rows={2}
              maxLength={500}
              showCount
            />
          </Form.Item>
          <Form.Item label="环境变量">
            <EnvVarEditor
              name="envVars"
              keyPlaceholder="变量名"
              valuePlaceholder="变量值"
              addButtonText="+ 添加环境变量"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
