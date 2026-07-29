import { useEffect, useMemo, useState } from 'react'
import {
  Alert,
  Button,
  Collapse,
  Divider,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Select,
  Space,
  Tag,
} from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import ImageSelect from '@/components/ImageSelect'
import EnvVarEditor from '@/components/EnvVarEditor'
import ResourceAwarePanel from '@/components/ResourceAwarePanel'
import { createInferenceService } from '@/services/inference'
import type { InferenceServiceCreateResult } from '@/services/inference'
import { getModel } from '@/services/models'
import { getBusinessConfigs } from '@/services/business-configs'
import { getMessageInstance } from '@/utils/messageHolder'

interface FormValues {
  name: string
  description?: string
  imageId: string
  containerPort: number
  subpathMode: 'rewrite' | 'native'
  command?: string
  args?: string
  envVars?: { key?: string; value?: string }[]
  gpuCount: number
  cpu: string
  memory: string
  replicas: number
  scalingMode: 'fixed' | 'auto'
  minReplicas?: number
  maxReplicas?: number
  targetMetricType?: 'gpu' | 'cpu'
  targetMetricValue?: number
  cooldownPeriod?: number
  pollingInterval?: number
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

interface DeployModalProps {
  open: boolean
  modelId: string
  /** 弹窗打开时默认选中的模型版本 ID (e.g. 最新可用版本); 用户可在弹窗内切换. */
  defaultVersionId?: string
  onClose: () => void
  onSuccess: (result: InferenceServiceCreateResult) => void
}

/** 简单 k8s 名字 sanitize: 与后端 sanitize_k8s_name 行为对齐 (lowercase + 非字母数字转 '-'). */
function sanitizeName(name: string): string {
  const cleaned = name
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
  return cleaned || 'default'
}

const VERSION_STATUS_LABEL: Record<string, string> = {
  uploading: '上传中',
  available: '可用',
  failed: '上传失败',
}

export default function DeployModal({
  open,
  modelId,
  defaultVersionId,
  onClose,
  onSuccess,
}: DeployModalProps) {
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)
  const scalingMode = Form.useWatch('scalingMode', form) ?? 'fixed'
  const [selectedVersionId, setSelectedVersionId] = useState<string | undefined>(defaultVersionId)

  // 拉模型详情: 拿到 name + 所有 versions 供用户选.
  const { data: modelDetail } = useQuery({
    queryKey: ['model-for-deploy', modelId],
    queryFn: () => getModel(modelId),
    enabled: open && !!modelId,
  })

  const { data: configsData } = useQuery({
    queryKey: ['business-configs-list', 1, 100],
    queryFn: () => getBusinessConfigs({ current: 1, pageSize: 100 }),
    enabled: open,
  })
  const configs = configsData?.items ?? []

  const modelName = modelDetail?.name ?? ''
  const versions = useMemo(
    () => (modelDetail?.versions ? [...modelDetail.versions].reverse() : []),
    [modelDetail?.versions],
  )

  const selectedVersion = versions.find((v) => v.id === selectedVersionId)

  // 弹窗打开时初始化版本选择: 优先 defaultVersionId, 否则取最新 available, 否则取 versions 第一个.
  useEffect(() => {
    if (!open) return
    if (defaultVersionId && versions.some((v) => v.id === defaultVersionId)) {
      setSelectedVersionId(defaultVersionId)
      return
    }
    const fallback = versions.find((v) => v.status === 'available') ?? versions[0]
    if (fallback) setSelectedVersionId(fallback.id)
  }, [open, defaultVersionId, versions])

  // 弹窗打开或版本变化时, 重置非模型相关字段默认值.
  useEffect(() => {
    if (!open) return
    form.setFieldsValue({
      containerPort: 8080,
      subpathMode: 'rewrite',
      gpuCount: 0,
      cpu: '2',
      memory: '4Gi',
      replicas: 1,
      scalingMode: 'fixed',
      minReplicas: 0,
      maxReplicas: 5,
      targetMetricType: 'cpu',
      targetMetricValue: 70,
      cooldownPeriod: 300,
      pollingInterval: 30,
    })
  }, [open, selectedVersionId, form])

  const handleSubmit = async () => {
    if (!selectedVersion) {
      getMessageInstance()?.error('请选择模型版本')
      return
    }
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
        modelVersionId: selectedVersion.id,
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
      onSuccess(res)
    } catch {
      // error handled by interceptor / form validation
    } finally {
      setSubmitting(false)
    }
  }

  const noAvailableVersion = !versions.some((v) => v.status === 'available')

  return (
    <Modal
      title={
        <Space>
          <ThunderboltOutlined />
          部署为推理服务
        </Space>
      }
      open={open}
      onCancel={onClose}
      width={920}
      destroyOnHidden
      footer={[
        <Button key="cancel" onClick={onClose}>
          取消
        </Button>,
        <Button
          key="submit"
          type="primary"
          loading={submitting}
          disabled={!selectedVersion}
          onClick={handleSubmit}
        >
          确认部署
        </Button>,
      ]}
    >
      <div style={{ display: 'flex', gap: 24, marginTop: 8 }}>
        <div style={{ flex: 2, minWidth: 0 }}>
          <Form<FormValues> form={form} layout="vertical">
            <Form.Item label="模型">
              <Space size={8} wrap>
                <Tag color="blue">{modelName || '加载中…'}</Tag>
                <Select
                  value={selectedVersionId}
                  onChange={setSelectedVersionId}
                  placeholder="选择模型版本"
                  style={{ minWidth: 180 }}
                  optionFilterProp="label"
                  disabled={versions.length === 0}
                >
                  {versions.map((v) => {
                    const statusLabel = VERSION_STATUS_LABEL[v.status] ?? v.status
                    const disabled = v.status !== 'available'
                    return (
                      <Select.Option
                        key={v.id}
                        value={v.id}
                        disabled={disabled}
                        label={`v${v.versionNumber}`}
                      >
                        <Space>
                          <span>v{v.versionNumber}</span>
                          <Tag color={disabled ? 'default' : 'success'}>{statusLabel}</Tag>
                        </Space>
                      </Select.Option>
                    )
                  })}
                </Select>
              </Space>
            </Form.Item>

            {noAvailableVersion && (
              <Alert
                type="warning"
                showIcon
                message="该模型当前没有可用的版本（需状态为「可用」），无法部署"
                style={{ marginBottom: 16 }}
              />
            )}

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
              extra={
                selectedVersion
                  ? `默认基于「${modelName} v${selectedVersion.versionNumber}」命名, 可修改`
                  : undefined
              }
            >
              <Input
                placeholder={
                  selectedVersion
                    ? `如 ${sanitizeName(modelName)}-v${selectedVersion.versionNumber}`
                    : '如 my-model-v3'
                }
                maxLength={100}
                showCount
              />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <Input.TextArea placeholder="服务描述（可选）" rows={2} />
            </Form.Item>

            <Form.Item
              name="imageId"
              label="运行时镜像"
              rules={[{ required: true, message: '请选择运行时镜像' }]}
              extra="推理运行时镜像（如 vLLM/TGI/Triton）；模型文件将通过共享卷挂载到 /kubeai/models/"
            >
              <ImageSelect placeholder="请选择推理运行时镜像" category="inference" />
            </Form.Item>
            <Form.Item
              name="containerPort"
              label="容器端口"
              rules={[{ required: true, message: '请输入容器端口' }]}
            >
              <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="如 8080" />
            </Form.Item>
            <Form.Item
              name="subpathMode"
              label="子路径模式"
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
              <EnvVarEditor
                name="envVars"
                keyPlaceholder="变量名"
                valuePlaceholder="变量值"
                addButtonText="+ 添加环境变量"
                presets={configs}
              />
            </Form.Item>

            <Divider>资源配置</Divider>

            <Form.Item name="gpuCount" label="GPU 数量" rules={[{ required: true }]}>
              <InputNumber min={0} max={16} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="cpu" label="CPU（核）" rules={[{ required: true }]}>
              <InputNumber min={1} max={128} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="memory" label="内存" rules={[{ required: true }]}>
              <Select options={MEMORY_OPTIONS} />
            </Form.Item>
            <Form.Item name="replicas" label="副本数" rules={[{ required: true }]}>
              <InputNumber min={1} max={10} style={{ width: '100%' }} />
            </Form.Item>

            <Divider>伸缩模式</Divider>

            <Form.Item name="scalingMode" label="伸缩模式">
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
                    rules={[{ required: true, message: '请输入最小副本数' }]}
                    style={{ flex: 1 }}
                  >
                    <InputNumber min={0} max={100} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item
                    name="maxReplicas"
                    label="最大副本数"
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
                    rules={[{ required: true, message: '请选择指标类型' }]}
                    style={{ flex: 1 }}
                  >
                    <Select options={METRIC_TYPE_OPTIONS} />
                  </Form.Item>
                  <Form.Item
                    name="targetMetricValue"
                    label="目标值"
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
                            style={{ flex: 1 }}
                          >
                            <InputNumber min={0} max={3600} style={{ width: '100%' }} />
                          </Form.Item>
                          <Form.Item
                            name="pollingInterval"
                            label="轮询间隔（秒）"
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
          </Form>
        </div>
        <div style={{ flex: 1, minWidth: 220, maxWidth: 300 }}>
          <div style={{ position: 'sticky', top: 16 }}>
            <ResourceAwarePanel />
          </div>
        </div>
      </div>
    </Modal>
  )
}
