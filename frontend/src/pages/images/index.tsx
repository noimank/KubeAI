import { useState, useCallback } from 'react'
import { Button, Empty, Form, Input, Modal, Popconfirm, Space, Table, Tag } from 'antd'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons'
import type { TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { createImage, deleteImage, getImages, toggleImage, updateImage } from '@/services/images'
import type { Image, ImageCreateParams, ImageUpdateParams } from '@/types/image'

export default function ImagesPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const [modalOpen, setModalOpen] = useState(false)
  const [editingImage, setEditingImage] = useState<Image | null>(null)
  const [form] = Form.useForm()

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canManage = hasPermission('images:manage')

  const { data, isLoading } = useQuery({
    queryKey: ['images', page, pageSize, keyword],
    queryFn: () =>
      getImages({
        current: page,
        pageSize,
        keyword,
      }),
  })

  const createMutation = useMutation({
    mutationFn: (values: ImageCreateParams) => createImage(values),
    onSuccess: () => {
      getMessageInstance()?.success('镜像创建成功')
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: ImageUpdateParams }) => updateImage(id, data),
    onSuccess: () => {
      getMessageInstance()?.success('镜像更新成功')
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
  })

  const toggleMutation = useMutation({
    mutationFn: (id: string) => toggleImage(id),
    onSuccess: (img) => {
      getMessageInstance()?.success(img.isEnabled ? '镜像已启用' : '镜像已禁用')
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteImage(id),
    onSuccess: () => {
      getMessageInstance()?.success('镜像删除成功')
      queryClient.invalidateQueries({ queryKey: ['images'] })
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

  const openCreateModal = () => {
    setEditingImage(null)
    form.resetFields()
    setModalOpen(true)
  }

  const openEditModal = (record: Image) => {
    setEditingImage(record)
    form.setFieldsValue({
      name: record.name,
      tag: record.tag,
      imageRef: record.imageRef,
      description: record.description,
    })
    setModalOpen(true)
  }

  const closeModal = () => {
    setModalOpen(false)
    setEditingImage(null)
    form.resetFields()
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    if (editingImage) {
      updateMutation.mutate({ id: editingImage.id, data: values })
    } else {
      createMutation.mutate(values)
    }
  }

  const columns = [
    {
      title: '名称',
      dataIndex: 'name',
      ellipsis: true,
      width: 180,
    },
    {
      title: '标签',
      dataIndex: 'tag',
      ellipsis: true,
      width: 160,
    },
    {
      title: '镜像地址',
      dataIndex: 'imageRef',
      ellipsis: true,
    },
    {
      title: '状态',
      dataIndex: 'isEnabled',
      width: 80,
      render: (val: boolean) => (
        <Tag color={val ? 'success' : 'default'}>{val ? '启用' : '禁用'}</Tag>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
    },
    {
      title: '操作',
      width: 200,
      render: (_: unknown, record: Image) => (
        <Space size="small">
          {canManage && (
            <Button type="link" size="small" onClick={() => openEditModal(record)}>
              编辑
            </Button>
          )}
          {canManage && (
            <Popconfirm
              title={record.isEnabled ? '确认禁用该镜像？' : '确认启用该镜像？'}
              description={
                record.isEnabled
                  ? '禁用后该镜像不会出现在用户选择列表中'
                  : '启用后该镜像将出现在用户选择列表中'
              }
              onConfirm={() => toggleMutation.mutate(record.id)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" size="small">
                {record.isEnabled ? '禁用' : '启用'}
              </Button>
            </Popconfirm>
          )}
          {canManage && (
            <Popconfirm
              title="确认删除该镜像？"
              description="删除后不可恢复，请谨慎操作。"
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

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Space>
          <Input.Search
            placeholder="搜索镜像名称"
            allowClear
            style={{ width: 320 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
            prefix={<SearchOutlined />}
          />
        </Space>
        {canManage && (
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
            添加镜像
          </Button>
        )}
      </div>
      <Table<Image>
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
            <Empty description="还没有预置镜像，添加第一个镜像开始吧">
              {canManage && (
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
                  添加镜像
                </Button>
              )}
            </Empty>
          ),
        }}
      />

      <Modal
        title={editingImage ? '编辑镜像' : '添加镜像'}
        open={modalOpen}
        onCancel={closeModal}
        onOk={handleSubmit}
        confirmLoading={createMutation.isPending || updateMutation.isPending}
        okText={editingImage ? '保存' : '添加'}
        cancelText="取消"
        destroyOnHidden
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="name"
            label="名称"
            rules={[
              { required: true, message: '请输入镜像名称' },
              { max: 200, message: '名称不能超过200字符' },
            ]}
          >
            <Input placeholder="如 PyTorch 2.1" maxLength={200} showCount />
          </Form.Item>
          <Form.Item
            name="tag"
            label="镜像标签"
            rules={[
              { required: true, message: '请输入镜像标签' },
              { max: 100, message: '标签不能超过100字符' },
            ]}
          >
            <Input placeholder="如 2.1.0-cuda12.1" maxLength={100} showCount />
          </Form.Item>
          <Form.Item
            name="imageRef"
            label="完整镜像地址"
            rules={[
              { required: true, message: '请输入镜像地址' },
              { max: 500, message: '地址不能超过500字符' },
            ]}
          >
            <Input placeholder="如 pytorch/pytorch:2.1.0-cuda12.1-cudnn8-runtime" maxLength={500} />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="镜像描述（可选）" rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
