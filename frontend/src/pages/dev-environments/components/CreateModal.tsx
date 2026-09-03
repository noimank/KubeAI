import { useState, useMemo } from 'react'
import { Alert, Form, Input, InputNumber, Modal, Select, Space } from 'antd'
import { CodeOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { getSelectableDevEnvironmentImages } from '@/services/dev-environment-images'
import { getDatasets, getDatasetDetail } from '@/services/datasets'
import { getAlgorithm } from '@/services/algorithms'
import { getBusinessConfigs } from '@/services/business-configs'
import EnvVarEditor from '@/components/EnvVarEditor'
import type { DevEnvironmentCreateParams } from '@/types/dev-environment'
import type { EnvironmentType } from '@/types/dev-environment-image'
import { ENVIRONMENT_TYPE_LABELS } from '@/types/dev-environment-image'

const ENVIRONMENT_TYPE_OPTIONS = Object.entries(ENVIRONMENT_TYPE_LABELS).map(([value, label]) => ({
  label,
  value,
}))

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

interface CreateModalProps {
  open: boolean
  algorithmId: string | null
  submitting: boolean
  onClose: () => void
  onSubmit: (values: DevEnvironmentCreateParams) => void
}

export function CreateModal({
  open,
  algorithmId,
  submitting,
  onClose,
  onSubmit,
}: CreateModalProps) {
  const [form] = Form.useForm<DevEnvironmentFormValues>()
  const [selectedDatasetId, setSelectedDatasetId] = useState<string | null>(null)
  const selectedEnvType = Form.useWatch('environmentType', form)

  const { data: images } = useQuery({
    queryKey: ['devEnvironmentImages-for-env'],
    queryFn: () => getSelectableDevEnvironmentImages(),
    enabled: open,
  })

  const { data: datasetsData } = useQuery({
    queryKey: ['datasets-for-env'],
    queryFn: () => getDatasets({ current: 1, pageSize: 100 }),
    enabled: open,
  })

  const { data: datasetDetail } = useQuery({
    queryKey: ['dataset-versions-for-env', selectedDatasetId],
    queryFn: () => getDatasetDetail(selectedDatasetId!),
    enabled: !!selectedDatasetId && open,
  })

  const { data: algoForEnv } = useQuery({
    queryKey: ['algorithm-for-dev-env', algorithmId],
    queryFn: () => getAlgorithm(algorithmId!),
    enabled: !!algorithmId && open,
  })

  const { data: configsData } = useQuery({
    queryKey: ['business-configs-list', 1, 100],
    queryFn: () => getBusinessConfigs({ current: 1, pageSize: 100 }),
    enabled: open,
  })
  const configs = configsData?.items ?? []

  const filteredImages = useMemo(
    () =>
      selectedEnvType
        ? (images?.filter((img) => img.environmentType === selectedEnvType) ?? [])
        : [],
    [images, selectedEnvType],
  )

  const handleClose = () => {
    form.resetFields()
    setSelectedDatasetId(null)
    onClose()
  }

  const handleImageSelect = (imageId: string) => {
    const selected = images?.find((img) => img.id === imageId)
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
        if (key) acc[key] = item.value ?? ''
        return acc
      }, {})

      onSubmit({
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
      })
    } catch {
      // validation failed
    }
  }

  const title =
    algorithmId && algoForEnv ? `从算法「${algoForEnv.name}」创建开发环境` : '创建开发环境'

  return (
    <Modal
      title={title}
      open={open}
      onCancel={handleClose}
      onOk={handleSubmit}
      confirmLoading={submitting}
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
            options={ENVIRONMENT_TYPE_OPTIONS}
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
            loading={!images}
            disabled={!selectedEnvType}
            onChange={handleImageSelect}
            notFoundContent={selectedEnvType ? '该类型暂无可用镜像' : '请先选择环境类型'}
            options={filteredImages.map((img) => ({ label: img.name, value: img.id }))}
          />
        </Form.Item>
        <Space size="middle" style={{ width: '100%' }}>
          <Form.Item name="gpuCount" label="GPU 数量" style={{ width: 120 }}>
            <InputNumber min={0} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="cpu" label="CPU" rules={[{ required: true, message: '请输入 CPU' }]}>
            <Input placeholder="如 2" style={{ width: 100 }} />
          </Form.Item>
          <Form.Item name="memory" label="内存" rules={[{ required: true, message: '请输入内存' }]}>
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
          <EnvVarEditor keyPlaceholder="Key" valuePlaceholder="Value" presets={configs} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
