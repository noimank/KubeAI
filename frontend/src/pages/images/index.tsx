import { useState, useCallback } from 'react'
import {
  Button,
  Drawer,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Segmented,
  Space,
  Table,
  Tag,
} from 'antd'
import { BuildOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import type { TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import {
  createImage,
  deleteImage,
  getBuildLog,
  getImages,
  rebuildImage,
  toggleImage,
  updateImage,
  buildImage,
} from '@/services/images'
import type { Image, ImageCreateParams, ImageUpdateParams, BuildStatus } from '@/types/image'

const BUILD_STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'warning', text: '排队中' },
  building: { color: 'processing', text: '构建中' },
  pushing: { color: 'processing', text: '推送中' },
  succeeded: { color: 'success', text: '成功' },
  failed: { color: 'error', text: '失败' },
}

const SOURCE_TABS = [
  { label: '全部', value: 'all' },
  { label: '预置', value: 'preset' },
  { label: '自定义', value: 'custom' },
]

export default function ImagesPage() {
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')
  const [sourceFilter, setSourceFilter] = useState<string>('all')

  const [modalOpen, setModalOpen] = useState(false)
  const [editingImage, setEditingImage] = useState<Image | null>(null)
  const [form] = Form.useForm()

  const [buildModalOpen, setBuildModalOpen] = useState(false)
  const [buildForm] = Form.useForm()

  const [logDrawerOpen, setLogDrawerOpen] = useState(false)
  const [logImageId, setLogImageId] = useState<string | null>(null)

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canManage = hasPermission('images:manage')
  const canBuild = hasPermission('images:build')

  const { data, isLoading } = useQuery({
    queryKey: ['images', page, pageSize, keyword, sourceFilter],
    queryFn: () =>
      getImages({
        current: page,
        pageSize,
        keyword,
        source: sourceFilter === 'all' ? undefined : sourceFilter,
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

  const buildMutation = useMutation({
    mutationFn: buildImage,
    onSuccess: () => {
      getMessageInstance()?.success('构建任务已提交')
      setBuildModalOpen(false)
      buildForm.resetFields()
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
  })

  const rebuildMutation = useMutation({
    mutationFn: rebuildImage,
    onSuccess: () => {
      getMessageInstance()?.success('重新构建已提交')
      queryClient.invalidateQueries({ queryKey: ['images'] })
    },
  })

  const { data: logData } = useQuery({
    queryKey: ['buildLog', logImageId],
    queryFn: () => getBuildLog(logImageId!),
    enabled: !!logImageId && logDrawerOpen,
    refetchInterval: logDrawerOpen && logImageId ? 3000 : false,
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

  const openBuildModal = () => {
    buildForm.resetFields()
    buildForm.setFieldsValue({ tag: 'latest' })
    setBuildModalOpen(true)
  }

  const handleBuildSubmit = async () => {
    const values = await buildForm.validateFields()
    buildMutation.mutate(values)
  }

  const openLogDrawer = (id: string) => {
    setLogImageId(id)
    setLogDrawerOpen(true)
  }

  const closeLogDrawer = () => {
    setLogDrawerOpen(false)
    setLogImageId(null)
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
      title: '来源',
      dataIndex: 'source',
      width: 80,
      render: (val: string) => (
        <Tag color={val === 'custom' ? 'purple' : 'default'}>
          {val === 'custom' ? '自定义' : '预置'}
        </Tag>
      ),
    },
    {
      title: '构建状态',
      dataIndex: 'buildStatus',
      width: 100,
      render: (val: BuildStatus | undefined) => {
        if (!val) return <Tag>—</Tag>
        const cfg = BUILD_STATUS_CONFIG[val] || { color: 'default', text: val }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '启用',
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
      width: 280,
      render: (_: unknown, record: Image) => (
        <Space size="small">
          {record.source === 'custom' && record.buildStatus && (
            <Button type="link" size="small" onClick={() => openLogDrawer(record.id)}>
              日志
            </Button>
          )}
          {record.source === 'custom' && record.buildStatus === 'failed' && canBuild && (
            <Popconfirm
              title="确认重新构建？"
              description="将使用原配置重新触发构建"
              onConfirm={() => rebuildMutation.mutate(record.id)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" size="small" icon={<BuildOutlined />}>
                重建
              </Button>
            </Popconfirm>
          )}
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
          <Segmented
            options={SOURCE_TABS}
            value={sourceFilter}
            onChange={(val) => {
              setSourceFilter(val as string)
              setPage(1)
            }}
          />
          <Input.Search
            placeholder="搜索镜像名称"
            allowClear
            style={{ width: 280 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
            prefix={<SearchOutlined />}
          />
        </Space>
        <Space>
          {canBuild && (
            <Button icon={<BuildOutlined />} onClick={openBuildModal}>
              构建自定义镜像
            </Button>
          )}
          {canManage && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
              添加镜像
            </Button>
          )}
        </Space>
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
            <Empty description="还没有镜像，添加第一个镜像开始吧">
              {canManage && (
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
                  添加镜像
                </Button>
              )}
            </Empty>
          ),
        }}
      />

      {/* 添加/编辑预置镜像 Modal */}
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

      {/* 构建自定义镜像 Modal */}
      <Modal
        title="构建自定义镜像"
        open={buildModalOpen}
        onCancel={() => {
          setBuildModalOpen(false)
          buildForm.resetFields()
        }}
        onOk={handleBuildSubmit}
        confirmLoading={buildMutation.isPending}
        okText="提交构建"
        cancelText="取消"
        width={640}
        destroyOnHidden
      >
        <Form form={buildForm} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="dockerfile"
            label="Dockerfile"
            rules={[{ required: true, message: '请输入 Dockerfile 内容' }]}
          >
            <Input.TextArea
              placeholder={'FROM python:3.12-slim\nRUN pip install numpy pandas'}
              rows={10}
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
          <Form.Item
            name="name"
            label="目标镜像名称"
            rules={[
              { required: true, message: '请输入目标镜像名称' },
              { max: 200, message: '名称不能超过200字符' },
            ]}
          >
            <Input placeholder="如 my-training-env" maxLength={200} showCount />
          </Form.Item>
          <Form.Item
            name="tag"
            label="目标标签"
            rules={[
              { required: true, message: '请输入目标标签' },
              { max: 100, message: '标签不能超过100字符' },
            ]}
          >
            <Input placeholder="如 v1.0" maxLength={100} showCount />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="镜像描述（可选）" rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 构建日志 Drawer */}
      <Drawer
        title="构建日志"
        open={logDrawerOpen}
        onClose={closeLogDrawer}
        width={720}
        styles={{ body: { padding: 0 } }}
      >
        {logData?.buildStatus && (
          <div style={{ padding: '12px 16px', borderBottom: '1px solid #f0f0f0' }}>
            <Tag color={BUILD_STATUS_CONFIG[logData.buildStatus]?.color || 'default'}>
              {BUILD_STATUS_CONFIG[logData.buildStatus]?.text || logData.buildStatus}
            </Tag>
          </div>
        )}
        <pre
          style={{
            padding: 16,
            margin: 0,
            fontSize: 13,
            fontFamily: 'monospace',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all',
            maxHeight: 'calc(100vh - 120px)',
            overflow: 'auto',
          }}
        >
          {logData?.log || '暂无日志'}
        </pre>
      </Drawer>
    </div>
  )
}
