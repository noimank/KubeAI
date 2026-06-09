import { useState, useCallback, useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Segmented,
  Select,
  Space,
  Table,
  Tag,
} from 'antd'
import { PlusOutlined, SearchOutlined, CodeOutlined } from '@ant-design/icons'
import type { TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { useAuthStore } from '@/stores/authStore'
import { getDatasets, getDatasetDetail } from '@/services/datasets'
import { getSelectableDevEnvironmentImages } from '@/services/dev-environment-images'
import { getAlgorithm } from '@/services/algorithms'
import {
  getDevEnvironments,
  createDevEnvironment,
  stopDevEnvironment,
  startDevEnvironment,
  deleteDevEnvironment,
  getAccessUrl,
} from '@/services/dev-environments'
import type {
  DevEnvironment,
  DevEnvironmentStatus,
  DevEnvironmentCreateParams,
} from '@/types/dev-environment'
import type { EnvironmentType } from '@/types/dev-environment-image'
import { ENVIRONMENT_TYPE_LABELS, ENVIRONMENT_TYPE_COLORS } from '@/types/dev-environment-image'

const STATUS_CONFIG: Record<DevEnvironmentStatus, { color: string; text: string }> = {
  pending: { color: 'warning', text: '排队中' },
  creating: { color: 'processing', text: '创建中' },
  running: { color: 'processing', text: '运行中' },
  stopped: { color: 'default', text: '已停止' },
  failed: { color: 'error', text: '失败' },
}

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '排队中', value: 'pending' },
  { label: '创建中', value: 'creating' },
  { label: '运行中', value: 'running' },
  { label: '已停止', value: 'stopped' },
  { label: '失败', value: 'failed' },
]

interface DevEnvironmentFormValues {
  name: string
  environmentType: EnvironmentType
  environmentImageId: string
  gpuCount?: number
  cpu?: string
  memory?: string
  description?: string
  datasetId?: string
  versionId?: string
  envVars?: { key?: string; value?: string }[]
}

export default function DevEnvironmentsPage() {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const algorithmId = searchParams.get('algorithmId')

  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [keyword, setKeyword] = useState<string | undefined>(undefined)
  const [searchText, setSearchText] = useState('')

  const [modalOpen, setModalOpen] = useState(!!algorithmId)
  const [form] = Form.useForm<DevEnvironmentFormValues>()

  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null)
  const selectedEnvType = Form.useWatch('environmentType', form)

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('dev_environments:write')
  const canManage = hasPermission('dev_environments:manage')
  const currentUserId = useAuthStore((s) => s.user?.id)

  const { data, isLoading } = useQuery({
    queryKey: ['devEnvironments', page, pageSize, statusFilter, keyword],
    queryFn: () =>
      getDevEnvironments({
        current: page,
        pageSize,
        status: statusFilter || undefined,
        name: keyword,
      }),
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? []
      const hasActive = items.some((env) => env.status === 'pending' || env.status === 'creating')
      return hasActive ? 5000 : false
    },
  })

  const createMutation = useMutation({
    mutationFn: (values: DevEnvironmentCreateParams) => createDevEnvironment(values),
    onSuccess: () => {
      getMessageInstance()?.success('开发环境创建任务已提交')
      setModalOpen(false)
      setSelectedDatasetId(null)
      form.resetFields()
      if (algorithmId) {
        navigate('/dev-environments', { replace: true })
      }
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopDevEnvironment,
    onSuccess: () => {
      getMessageInstance()?.success('停止任务已提交，请稍候')
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
    },
  })

  const startMutation = useMutation({
    mutationFn: startDevEnvironment,
    onSuccess: () => {
      getMessageInstance()?.success('启动任务已提交，请稍候')
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteDevEnvironment,
    onSuccess: () => {
      getMessageInstance()?.success('删除任务已提交')
      queryClient.invalidateQueries({ queryKey: ['devEnvironments'] })
    },
  })

  const { data: envImagesData } = useQuery({
    queryKey: ['devEnvironmentImages-for-env'],
    queryFn: () => getSelectableDevEnvironmentImages(),
    enabled: modalOpen,
  })

  const { data: datasetsData } = useQuery({
    queryKey: ['datasets-for-env'],
    queryFn: () => getDatasets({ current: 1, pageSize: 100 }),
    enabled: modalOpen,
  })

  const { data: datasetDetail } = useQuery({
    queryKey: ['dataset-versions-for-env', selectedDatasetId],
    queryFn: () => getDatasetDetail(selectedDatasetId!),
    enabled: !!selectedDatasetId && modalOpen,
  })

  const { data: algoForEnv } = useQuery({
    queryKey: ['algorithm-for-dev-env', algorithmId],
    queryFn: () => getAlgorithm(algorithmId!),
    enabled: !!algorithmId && modalOpen,
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const handleOpenEnvironment = async (envId: string) => {
    try {
      const res = await getAccessUrl(envId)
      if (res.accessUrl) {
        window.open(res.accessUrl, '_blank')
      }
    } catch {
      getMessageInstance()?.error('获取环境访问地址失败')
    }
  }

  const openCreateModal = () => {
    form.resetFields()
    setSelectedDatasetId(null)
    setModalOpen(true)
  }

  const closeCreateModal = () => {
    setModalOpen(false)
    setSelectedDatasetId(null)
    form.resetFields()
    if (algorithmId) {
      navigate('/dev-environments', { replace: true })
    }
  }

  const handleImageSelect = (imageId: string) => {
    const selected = envImagesData?.find((img) => img.id === imageId)
    if (selected) {
      form.setFieldsValue({
        cpu: selected.defaultCpu,
        memory: selected.defaultMemory,
        gpuCount: selected.defaultGpuCount,
      })
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const envVars = values.envVars?.reduce((acc: Record<string, string>, item) => {
        const key = item.key?.trim()
        if (key) {
          acc[key] = item.value ?? ''
        }
        return acc
      }, {})

      const params: DevEnvironmentCreateParams = {
        name: values.name,
        environmentImageId: values.environmentImageId,
        gpuCount: values.gpuCount ?? 0,
        cpu: values.cpu || '2',
        memory: values.memory || '4Gi',
        description: values.description,
        envVars: envVars && Object.keys(envVars).length > 0 ? envVars : undefined,
        datasets: values.datasetId
          ? [{ datasetId: values.datasetId, versionId: values.versionId }]
          : undefined,
        algorithmId: algorithmId ?? undefined,
      }
      createMutation.mutate(params)
    } catch {
      // validation failed
    }
  }

  const environmentTypeOptions = useMemo(
    () =>
      Object.entries(ENVIRONMENT_TYPE_LABELS).map(([value, label]) => ({
        label,
        value,
      })),
    [],
  )

  const filteredImages = useMemo(
    () =>
      selectedEnvType
        ? (envImagesData?.filter((img) => img.environmentType === selectedEnvType) ?? [])
        : [],
    [envImagesData, selectedEnvType],
  )

  const columns = [
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
      render: (datasets: DevEnvironment['mountedDatasets']) => {
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
      render: (val: string | undefined) => (val ? dayjs(val).format('YYYY-MM-DD HH:mm:ss') : '—'),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
      render: (val: string) => dayjs(val).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: '操作',
      width: 280,
      render: (_: unknown, record: DevEnvironment) => (
        <Space size="small">
          {record.status === 'running' && (
            <Button type="link" size="small" onClick={() => handleOpenEnvironment(record.id)}>
              打开环境
            </Button>
          )}
          {canWrite && ['running', 'creating', 'pending'].includes(record.status) && (
            <Popconfirm
              title="确认停止该环境？"
              description="停止后可以重新启动"
              onConfirm={() => stopMutation.mutate(record.id)}
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
              onConfirm={() => startMutation.mutate(record.id)}
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
            options={STATUS_TABS}
            value={statusFilter}
            onChange={(val) => {
              setStatusFilter(val as string)
              setPage(1)
            }}
          />
          <Input.Search
            placeholder="搜索环境名称"
            allowClear
            style={{ width: 280 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
            prefix={<SearchOutlined />}
          />
        </Space>
        <Space>
          {canWrite && (
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
              创建开发环境
            </Button>
          )}
        </Space>
      </div>

      <Table<DevEnvironment>
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
            <Empty description="还没有开发环境，创建一个开始编码">
              {canWrite && (
                <Button type="primary" icon={<PlusOutlined />} onClick={openCreateModal}>
                  创建开发环境
                </Button>
              )}
            </Empty>
          ),
        }}
      />

      <Modal
        title={
          algorithmId && algoForEnv ? `从算法「${algoForEnv.name}」创建开发环境` : '创建开发环境'
        }
        open={modalOpen}
        onCancel={closeCreateModal}
        onOk={handleSubmit}
        confirmLoading={createMutation.isPending}
        okText="创建"
        cancelText="取消"
        width={640}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          style={{ marginTop: 16 }}
          initialValues={{ gpuCount: 0, cpu: '2', memory: '4Gi' }}
        >
          {algorithmId && algoForEnv && (
            <Alert
              type="info"
              showIcon
              icon={<CodeOutlined />}
              message={`算法「${algoForEnv.name}」的文件将在环境启动时自动解压到用户家目录`}
              style={{ marginBottom: 16 }}
            />
          )}
          <Form.Item
            name="name"
            label="环境名称"
            rules={[
              { required: true, message: '请输入环境名称' },
              { max: 100, message: '名称不能超过100字符' },
            ]}
          >
            <Input placeholder="如 my-dev-env" maxLength={100} showCount />
          </Form.Item>
          <Form.Item
            name="environmentType"
            label="环境类型"
            rules={[{ required: true, message: '请选择环境类型' }]}
          >
            <Select
              placeholder="选择环境类型"
              onChange={(val: EnvironmentType) => {
                form.setFieldsValue({ environmentType: val, environmentImageId: undefined })
              }}
              options={environmentTypeOptions}
            />
          </Form.Item>
          <Form.Item
            name="environmentImageId"
            label="环境镜像"
            rules={[{ required: true, message: '请选择环境镜像' }]}
          >
            <Select
              placeholder={selectedEnvType ? '选择环境镜像' : '请先选择环境类型'}
              showSearch
              optionFilterProp="label"
              loading={!envImagesData}
              disabled={!selectedEnvType}
              onChange={handleImageSelect}
              notFoundContent={selectedEnvType ? '该类型暂无可用镜像' : '请先选择环境类型'}
              options={filteredImages.map((img) => ({
                label: img.name,
                value: img.id,
              }))}
            />
          </Form.Item>
          <Space size="middle" style={{ width: '100%' }}>
            <Form.Item name="gpuCount" label="GPU 数量" style={{ width: 120 }}>
              <InputNumber min={0} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="cpu" label="CPU" rules={[{ required: true, message: '请输入 CPU' }]}>
              <Input placeholder="如 2" style={{ width: 100 }} />
            </Form.Item>
            <Form.Item
              name="memory"
              label="内存"
              rules={[{ required: true, message: '请输入内存' }]}
            >
              <Input placeholder="如 4Gi" style={{ width: 100 }} />
            </Form.Item>
          </Space>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="环境描述（可选）" rows={2} />
          </Form.Item>
          <Form.Item name="datasetId" label="挂载数据集">
            <Select
              placeholder="选择数据集（可选）"
              allowClear
              showSearch
              optionFilterProp="label"
              loading={!datasetsData}
              onChange={(val) => {
                setSelectedDatasetId(val || null)
                form.setFieldValue('versionId', undefined)
              }}
              options={datasetsData?.items?.map((ds) => ({
                label: ds.displayName || ds.name,
                value: ds.id,
              }))}
            />
          </Form.Item>
          {selectedDatasetId && datasetDetail?.versions?.length ? (
            <Form.Item name="versionId" label="数据集版本">
              <Select
                placeholder="选择版本（可选，默认最新）"
                allowClear
                options={datasetDetail.versions.map((v) => ({
                  label: `v${v.versionNumber}${v.description ? ` - ${v.description}` : ''}`,
                  value: v.id,
                }))}
              />
            </Form.Item>
          ) : null}
          <Form.Item label="环境变量">
            <Form.List name="envVars">
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...restField }) => (
                    <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                      <Form.Item
                        {...restField}
                        name={[name, 'key']}
                        rules={[{ required: true, message: '请输入 Key' }]}
                      >
                        <Input placeholder="Key" />
                      </Form.Item>
                      <Form.Item {...restField} name={[name, 'value']}>
                        <Input placeholder="Value" />
                      </Form.Item>
                      <Button type="link" danger onClick={() => remove(name)}>
                        删除
                      </Button>
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add()} block>
                    + 添加环境变量
                  </Button>
                </>
              )}
            </Form.List>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
