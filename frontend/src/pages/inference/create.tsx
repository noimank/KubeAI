import { useEffect, useState } from 'react'
import {
  Button,
  Collapse,
  Descriptions,
  Divider,
  Form,
  Input,
  InputNumber,
  Radio,
  Select,
  Space,
  Steps,
  Tag,
} from 'antd'
import type { FormInstance } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import ResourceAwarePanel from '@/components/ResourceAwarePanel'
import ImageSelect from '@/components/ImageSelect'
import EnvVarEditor from '@/components/EnvVarEditor'
import { createInferenceService } from '@/services/inference'
import type { InferenceServiceCreateResult } from '@/services/inference'
import { getSelectableImages } from '@/services/images'
import { getModels, getModel } from '@/services/models'
import { getBusinessConfigs } from '@/services/business-configs'

interface FormValues {
  name: string
  gpuCount: number
  cpu: string
  memory: string
  replicas: number
  image?: string
  imageId?: string
  modelId?: string
  modelVersionId?: string
  containerPort?: number
  command?: string
  args?: string
  envVars?: { key?: string; value?: string }[]
  description?: string
  scalingMode?: 'fixed' | 'auto'
  minReplicas?: number
  maxReplicas?: number
  targetMetricType?: 'gpu' | 'cpu'
  targetMetricValue?: number
  cooldownPeriod?: number
  pollingInterval?: number
  subpathMode?: 'rewrite' | 'native'
}

const MEMORY_OPTIONS = [
  { label: '4 Gi', value: '4Gi' },
  { label: '8 Gi', value: '8Gi' },
  { label: '16 Gi', value: '16Gi' },
  { label: '32 Gi', value: '32Gi' },
  { label: '64 Gi', value: '64Gi' },
]

const METRIC_TYPE_OPTIONS = [
  { label: 'GPU 利用率', value: 'gpu' },
  { label: 'CPU 利用率', value: 'cpu' },
]

export default function CreateInferenceServicePage() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState(0)
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)

  const scalingMode = Form.useWatch('scalingMode', form) ?? 'fixed'

  const { data: modelsData } = useQuery({
    queryKey: ['models-for-inference', 1, 100],
    queryFn: () => getModels({ current: 1, pageSize: 100 }),
  })
  const models = modelsData?.items ?? []

  const selectedModelId = Form.useWatch('modelId', form)
  const { data: modelDetail } = useQuery({
    queryKey: ['model-detail-for-inference', selectedModelId],
    queryFn: () => (selectedModelId ? getModel(selectedModelId) : Promise.resolve(null)),
    enabled: !!selectedModelId,
  })
  const versions = modelDetail?.versions ?? []

  const selectedModelVersionId = Form.useWatch('modelVersionId', form)
  const selectedModelVersion = versions.find((v) => v.id === selectedModelVersionId)

  // 选择模型版本后, 用该版本的部署配置预填容器/资源字段 (仅覆盖配置中实际有值的字段)
  useEffect(() => {
    const cfg = selectedModelVersion?.deployConfig
    if (!cfg) return
    const patch: Partial<FormValues> = {}
    if (cfg.images?.length) patch.imageId = cfg.images[0].imageId
    if (cfg.containerPort != null) patch.containerPort = cfg.containerPort
    if (cfg.subpathMode) patch.subpathMode = cfg.subpathMode
    if (cfg.command?.length) patch.command = cfg.command.join(' ')
    if (cfg.args?.length) patch.args = cfg.args.join(' ')
    if (cfg.envVars && Object.keys(cfg.envVars).length > 0) {
      patch.envVars = Object.entries(cfg.envVars).map(([key, value]) => ({ key, value }))
    }
    if (cfg.gpuCount != null) patch.gpuCount = cfg.gpuCount
    if (cfg.cpu) patch.cpu = cfg.cpu
    if (cfg.memory) patch.memory = cfg.memory
    if (cfg.replicas != null) patch.replicas = cfg.replicas
    if (Object.keys(patch).length > 0) {
      form.setFieldsValue(patch)
      getMessageInstance()?.info('已应用该模型版本的部署配置，可按需调整')
    }
  }, [selectedModelVersion, form])

  const { data: configsData } = useQuery({
    queryKey: ['business-configs-list', 1, 100],
    queryFn: () => getBusinessConfigs({ current: 1, pageSize: 100 }),
  })
  const configs = configsData?.items ?? []

  const handleNext = async () => {
    try {
      const fields =
        current === 0
          ? ['name', 'imageId', 'containerPort']
          : current === 1
            ? ['gpuCount', 'cpu', 'memory', 'replicas']
            : []
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
      const isAuto = values.scalingMode === 'auto'

      const envVars = values.envVars?.reduce((acc: Record<string, string>, item) => {
        const key = item.key?.trim()
        if (key) acc[key] = item.value ?? ''
        return acc
      }, {})

      const res: InferenceServiceCreateResult = await createInferenceService({
        name: values.name,
        gpuCount: values.gpuCount,
        cpu: String(values.cpu),
        memory: values.memory,
        replicas: values.replicas,
        imageId: values.imageId,
        modelVersionId: values.modelVersionId || undefined,
        containerPort: values.containerPort,
        command: values.command ? values.command.split(/\s+/).filter(Boolean) : undefined,
        args: values.args ? values.args.split(/\s+/).filter(Boolean) : undefined,
        envVars: envVars && Object.keys(envVars).length > 0 ? envVars : undefined,
        description: values.description || undefined,
        subpathMode: values.subpathMode,
        autoScaling: isAuto
          ? {
              scalingMode: 'auto',
              minReplicas: values.minReplicas ?? 0,
              maxReplicas: values.maxReplicas ?? 5,
              targetMetricType: values.targetMetricType,
              targetMetricValue: values.targetMetricValue,
              cooldownPeriod: values.cooldownPeriod ?? 300,
              pollingInterval: values.pollingInterval ?? 30,
            }
          : undefined,
      })
      getMessageInstance()?.success('推理服务创建任务已提交')
      navigate(`/inference/${res.id}`, { state: { authToken: res.authToken } })
    } catch {
      // error handled by interceptor
    } finally {
      setSubmitting(false)
    }
  }

  const steps = [
    {
      title: '容器配置',
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

          {/* 运行时镜像 / 端口 / 命令. 模型/代码可打进镜像或放挂载的共享卷 (/kubeai/home, /kubeai/workspace). */}
          <Form.Item
            name="imageId"
            label="运行时镜像"
            rules={[{ required: true, message: '请选择运行时镜像' }]}
            extra="推理运行时镜像（如 vLLM/TGI/Triton）；模型/代码可打进镜像或放挂载的共享卷"
          >
            <ImageSelect placeholder="请选择推理运行时镜像" category="inference" />
          </Form.Item>
          <Form.Item
            name="containerPort"
            label="容器端口"
            rules={[{ required: true, message: '请输入容器端口' }]}
            initialValue={8080}
          >
            <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="如 8080" />
          </Form.Item>
          <Form.Item
            name="subpathMode"
            label="子路径模式"
            initialValue="rewrite"
            tooltip="应用是否自行处理 /inference/<hex> 访问前缀。重写：平台剥前缀，上游见原生路径（适用 vLLM/TGI 等不透明 API）；透传：前缀原样转发，应用读 BASE_URL_PREFIX 自行路由（适用 RemoteBash/Jupyter 等 Web 应用）"
          >
            <Radio.Group>
              <Radio value="rewrite">重写（剥前缀）</Radio>
              <Radio value="native">透传（保留前缀）</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item
            name="command"
            label="启动命令"
            extra="覆盖镜像默认 ENTRYPOINT，如 python main.py（须以 UID 1000 可写运行）"
          >
            <Input placeholder="如 python main.py" />
          </Form.Item>
          <Form.Item name="args" label="启动参数" extra="空格分隔，追加到命令之后">
            <Input placeholder="如 --host 0.0.0.0 --port 8080" />
          </Form.Item>

          <Form.Item label="环境变量">
            <EnvVarEditor presets={configs} />
          </Form.Item>

          {/* 可选: 从模型注册仓库选择模型版本 (模型文件经共享存储卷直接挂载到 /kubeai/models/). */}
          <Divider>模型（可选）</Divider>
          <Form.Item
            name="modelId"
            label="模型"
            extra="从模型注册仓库选择预注册模型，模型文件将通过共享存储卷直接挂载到 /kubeai/models/"
          >
            <Select
              placeholder="请选择模型（可选）"
              showSearch
              optionFilterProp="label"
              allowClear
              options={models.map((m) => ({ label: m.name, value: m.id }))}
              onChange={() => {
                form.setFieldValue('modelVersionId', undefined)
              }}
            />
          </Form.Item>
          <Form.Item name="modelVersionId" label="模型版本">
            <Select
              placeholder={selectedModelId ? '请选择模型版本' : '请先选择模型'}
              showSearch
              optionFilterProp="label"
              allowClear
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

          <Divider>伸缩模式</Divider>

          <Form.Item name="scalingMode" label="伸缩模式" initialValue="fixed">
            <Radio.Group>
              <Radio value="fixed">固定副本</Radio>
              <Radio value="auto">自动伸缩</Radio>
            </Radio.Group>
          </Form.Item>

          {scalingMode === 'auto' && (
            <>
              <div style={{ display: 'flex', gap: 16 }}>
                <Form.Item
                  name="minReplicas"
                  label="最小副本数"
                  initialValue={0}
                  rules={[{ required: true, message: '请输入最小副本数' }]}
                  style={{ flex: 1 }}
                >
                  <InputNumber min={0} max={100} style={{ width: '100%' }} />
                </Form.Item>
                <Form.Item
                  name="maxReplicas"
                  label="最大副本数"
                  initialValue={5}
                  rules={[{ required: true, message: '请输入最大副本数' }]}
                  style={{ flex: 1 }}
                >
                  <InputNumber min={1} max={100} style={{ width: '100%' }} />
                </Form.Item>
              </div>
              <div style={{ display: 'flex', gap: 16 }}>
                <Form.Item
                  name="targetMetricType"
                  label="目标指标"
                  initialValue="cpu"
                  rules={[{ required: true, message: '请选择指标类型' }]}
                  style={{ flex: 1 }}
                >
                  <Select options={METRIC_TYPE_OPTIONS} />
                </Form.Item>
                <Form.Item
                  name="targetMetricValue"
                  label="目标值"
                  initialValue={70}
                  rules={[{ required: true, message: '请输入目标值' }]}
                  style={{ flex: 1 }}
                >
                  <InputNumber min={1} style={{ width: '100%' }} />
                </Form.Item>
              </div>
              <Collapse
                size="small"
                items={[
                  {
                    key: 'advanced',
                    label: '高级配置',
                    children: (
                      <div style={{ display: 'flex', gap: 16 }}>
                        <Form.Item
                          name="cooldownPeriod"
                          label="冷却时间（秒）"
                          initialValue={300}
                          style={{ flex: 1 }}
                        >
                          <InputNumber min={0} max={3600} style={{ width: '100%' }} />
                        </Form.Item>
                        <Form.Item
                          name="pollingInterval"
                          label="轮询间隔（秒）"
                          initialValue={30}
                          style={{ flex: 1 }}
                        >
                          <InputNumber min={5} max={300} style={{ width: '100%' }} />
                        </Form.Item>
                      </div>
                    ),
                  },
                ]}
              />
            </>
          )}
        </>
      ),
    },
    {
      title: '确认部署',
      content: <ConfirmStep form={form} />,
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

function ConfirmStep({ form }: { form: FormInstance<FormValues> }) {
  const values = Form.useWatch<FormValues>([], form)
  const { data: selectableImages = [] } = useQuery({
    queryKey: ['selectableImages', 'inference'],
    queryFn: () => getSelectableImages('inference'),
  })

  const { data: modelsData } = useQuery({
    queryKey: ['models-for-inference', 1, 100],
    queryFn: () => getModels({ current: 1, pageSize: 100 }),
  })
  const models = modelsData?.items ?? []

  const { data: modelDetail } = useQuery({
    queryKey: ['model-detail-for-inference-confirm', values?.modelId],
    queryFn: () => (values?.modelId ? getModel(values.modelId!) : Promise.resolve(null)),
    enabled: !!values?.modelId,
  })
  const versions = modelDetail?.versions ?? []

  if (!values) return null

  const isAuto = values.scalingMode === 'auto'

  const selectedImage = values.imageId
    ? selectableImages.find((img) => img.id === values.imageId)
    : null
  const imageLabel = selectedImage ? `${selectedImage.name}:${selectedImage.tag}` : '—'

  const modelLabel = values.modelId
    ? (models.find((m) => m.id === values.modelId)?.name ?? '未选择')
    : '未选择'
  const selectedVersion = values.modelVersionId
    ? versions.find((v) => v.id === values.modelVersionId)
    : null

  return (
    <Descriptions column={2} bordered size="small">
      <Descriptions.Item label="服务名称" span={2}>
        {values.name}
      </Descriptions.Item>
      <Descriptions.Item label="描述" span={2}>
        {values.description || '—'}
      </Descriptions.Item>
      <Descriptions.Item label="运行时镜像" span={2}>
        <Tag>{imageLabel}</Tag>
      </Descriptions.Item>
      <Descriptions.Item label="模型" span={2}>
        {modelLabel}{' '}
        {selectedVersion ? <Tag color="blue">v{selectedVersion.versionNumber}</Tag> : '(未选择)'}
      </Descriptions.Item>
      <Descriptions.Item label="容器端口">{values.containerPort ?? '—'}</Descriptions.Item>
      <Descriptions.Item label="子路径模式">
        {values.subpathMode === 'native' ? <Tag color="blue">透传</Tag> : <Tag>重写</Tag>}
      </Descriptions.Item>
      <Descriptions.Item label="启动命令" span={2}>
        {values.command || <Tag>默认</Tag>}
      </Descriptions.Item>
      <Descriptions.Item label="启动参数" span={2}>
        {values.args || <Tag>默认</Tag>}
      </Descriptions.Item>
      {values.envVars && values.envVars.filter((e) => e?.key?.trim()).length > 0 ? (
        <Descriptions.Item label="环境变量" span={2}>
          {values.envVars
            .filter((e) => e?.key?.trim())
            .map((e, idx) => (
              <Tag key={idx} style={{ marginBottom: 4 }}>
                {e?.key?.trim()}={e?.value || ''}
              </Tag>
            ))}
        </Descriptions.Item>
      ) : null}
      <Descriptions.Item label="GPU">{values.gpuCount ?? 0} 张</Descriptions.Item>
      <Descriptions.Item label="CPU">{values.cpu} 核</Descriptions.Item>
      <Descriptions.Item label="内存">{values.memory}</Descriptions.Item>
      <Descriptions.Item label="副本数">{values.replicas ?? 1}</Descriptions.Item>
      <Descriptions.Item label="伸缩模式" span={2}>
        {isAuto ? (
          <Space>
            <Tag color="blue">自动伸缩</Tag>
            <span>
              {values.minReplicas}-{values.maxReplicas} 副本 |{' '}
              {values.targetMetricType === 'cpu' ? 'CPU 利用率' : 'GPU 利用率'} &gt;{' '}
              {values.targetMetricValue}
            </span>
          </Space>
        ) : (
          <Tag>固定副本</Tag>
        )}
      </Descriptions.Item>
    </Descriptions>
  )
}
