import { useState } from 'react'
import { Button, Descriptions, Form, Input, InputNumber, Select, Steps, Tag } from 'antd'
import type { FormInstance } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import ResourceAwarePanel from '@/components/ResourceAwarePanel'
import { createInferenceService } from '@/services/inference'
import type { InferenceServiceCreateResult } from '@/services/inference'
import { getModel, getModels } from '@/services/models'

interface FormValues {
  name: string
  modelId?: string
  modelVersionId: string
  gpuCount: number
  cpu: string
  memory: string
  replicas: number
  image?: string
  description?: string
}

const MEMORY_OPTIONS = [
  { label: '4 Gi', value: '4Gi' },
  { label: '8 Gi', value: '8Gi' },
  { label: '16 Gi', value: '16Gi' },
  { label: '32 Gi', value: '32Gi' },
  { label: '64 Gi', value: '64Gi' },
]

export default function CreateInferenceServicePage() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState(0)
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)

  const { data: modelsData } = useQuery({
    queryKey: ['models-for-inference', 1, 100],
    queryFn: () => getModels({ current: 1, pageSize: 100 }),
  })

  const models = modelsData?.items ?? []

  const [selectedModelId, setSelectedModelId] = useState<string | undefined>(undefined)

  const { data: modelDetail } = useQuery({
    queryKey: ['model-detail-for-inference', selectedModelId],
    queryFn: () => getModel(selectedModelId!),
    enabled: !!selectedModelId,
  })

  const versions = modelDetail?.versions ?? []

  const handleNext = async () => {
    try {
      const fields =
        current === 0
          ? ['name', 'modelId', 'modelVersionId']
          : ['gpuCount', 'cpu', 'memory', 'replicas']
      await form.validateFields(fields)
      setCurrent(current + 1)
    } catch {
      // validation failed
    }
  }

  const handlePrev = () => {
    setCurrent(current - 1)
  }

  const handleSubmit = async () => {
    try {
      setSubmitting(true)
      const values = await form.validateFields()
      const res: InferenceServiceCreateResult = await createInferenceService({
        name: values.name,
        modelVersionId: values.modelVersionId,
        gpuCount: values.gpuCount,
        cpu: String(values.cpu),
        memory: values.memory,
        replicas: values.replicas,
        image: values.image || undefined,
        description: values.description || undefined,
      })
      getMessageInstance()?.success('推理服务创建成功')
      navigate(`/inference/${res.id}`, { state: { authToken: res.authToken } })
    } catch {
      // error handled by interceptor
    } finally {
      setSubmitting(false)
    }
  }

  const steps = [
    {
      title: '选择模型版本',
      content: (
        <>
          <Form.Item
            name="name"
            label="服务名称"
            rules={[
              { required: true, message: '请输入服务名称' },
              {
                pattern: /^[a-z0-9][a-z0-9-]*[a-z0-9]$/,
                message: '仅支持小写字母、数字和中划线，且以字母或数字开头',
              },
            ]}
          >
            <Input placeholder="如 my-inference-service" maxLength={100} showCount />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="服务描述（可选）" rows={2} />
          </Form.Item>
          <Form.Item
            name="modelId"
            label="模型"
            rules={[{ required: true, message: '请选择模型' }]}
          >
            <Select
              placeholder="请选择模型"
              showSearch
              optionFilterProp="label"
              options={models.map((m) => ({ label: m.name, value: m.id }))}
              onChange={(val) => {
                setSelectedModelId(val)
                form.setFieldValue('modelVersionId', undefined)
              }}
            />
          </Form.Item>
          <Form.Item
            name="modelVersionId"
            label="模型版本"
            rules={[{ required: true, message: '请选择模型版本' }]}
          >
            <Select
              placeholder={selectedModelId ? '请选择模型版本' : '请先选择模型'}
              showSearch
              optionFilterProp="label"
              disabled={!selectedModelId}
              options={versions.map((v) => ({
                label: `v${v.versionNumber}`,
                value: v.id,
              }))}
            />
          </Form.Item>
        </>
      ),
    },
    {
      title: '资源配置',
      content: (
        <>
          <Form.Item name="gpuCount" label="GPU 数量" initialValue={0} rules={[{ required: true }]}>
            <InputNumber min={0} max={16} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="cpu" label="CPU（核）" initialValue="2" rules={[{ required: true }]}>
            <InputNumber min={1} max={128} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="memory" label="内存" initialValue="4Gi" rules={[{ required: true }]}>
            <Select options={MEMORY_OPTIONS} />
          </Form.Item>
          <Form.Item name="replicas" label="副本数" initialValue={1} rules={[{ required: true }]}>
            <InputNumber min={1} max={10} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="image" label="推理镜像" extra="留空使用 KServe 默认推理镜像">
            <Input placeholder="如 harbor.example.com/kubeai/sklearn-server:latest" />
          </Form.Item>
        </>
      ),
    },
    {
      title: '确认部署',
      content: <ConfirmStep form={form} models={models} versions={versions} />,
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      <Steps
        current={current}
        items={steps.map((s) => ({ title: s.title }))}
        style={{ marginBottom: 24 }}
      />
      <div style={{ display: 'flex', gap: 24 }}>
        <div style={{ flex: 2, maxWidth: 800 }}>
          <Form form={form} layout="vertical">
            {steps.map((step, index) => (
              <div key={index} style={{ display: index === current ? 'block' : 'none' }}>
                {step.content}
              </div>
            ))}
          </Form>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 12, marginTop: 24 }}>
            {current > 0 && <Button onClick={handlePrev}>上一步</Button>}
            {current < steps.length - 1 && (
              <Button type="primary" onClick={handleNext}>
                下一步
              </Button>
            )}
            {current === steps.length - 1 && (
              <Button type="primary" loading={submitting} onClick={handleSubmit}>
                确认部署
              </Button>
            )}
          </div>
        </div>
        <div style={{ flex: 1, minWidth: 260, maxWidth: 340 }}>
          <div style={{ position: 'sticky', top: 16 }}>
            <ResourceAwarePanel />
          </div>
        </div>
      </div>
    </div>
  )
}

function ConfirmStep({
  form,
  models,
  versions,
}: {
  form: FormInstance<FormValues>
  models: { id: string; name: string }[]
  versions: { id: string; versionNumber: number }[]
}) {
  const values = Form.useWatch<FormValues>([], form)
  if (!values) return null

  const modelLabel = values.modelId
    ? (models.find((m) => m.id === values.modelId)?.name ?? '未选择')
    : '未选择'
  const version = versions.find((v) => v.id === values.modelVersionId)
  const versionLabel = version ? `v${version.versionNumber}` : '—'

  return (
    <Descriptions column={2} bordered size="small">
      <Descriptions.Item label="服务名称">{values.name}</Descriptions.Item>
      <Descriptions.Item label="描述">{values.description || '—'}</Descriptions.Item>
      <Descriptions.Item label="模型">{modelLabel}</Descriptions.Item>
      <Descriptions.Item label="版本">
        <Tag color="blue">{versionLabel}</Tag>
      </Descriptions.Item>
      <Descriptions.Item label="GPU">{values.gpuCount ?? 0} 张</Descriptions.Item>
      <Descriptions.Item label="CPU">{values.cpu} 核</Descriptions.Item>
      <Descriptions.Item label="内存">{values.memory}</Descriptions.Item>
      <Descriptions.Item label="副本数">{values.replicas ?? 1}</Descriptions.Item>
      <Descriptions.Item label="推理镜像" span={2}>
        {values.image || <Tag>KServe 默认镜像</Tag>}
      </Descriptions.Item>
    </Descriptions>
  )
}
