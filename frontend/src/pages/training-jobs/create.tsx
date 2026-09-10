import { useEffect, useState } from 'react'
import {
  Alert,
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
  Switch,
  Tag,
  Tooltip,
  theme,
} from 'antd'
import {
  CheckCircleOutlined,
  DeleteOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  PlusOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import type { FormInstance } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import ImageSelect from '@/components/ImageSelect'
import ResourceAwarePanel from '@/components/ResourceAwarePanel'
import EnvVarEditor from '@/components/EnvVarEditor'
import { getDatasets, getDatasetDetail } from '@/services/datasets'
import { getSelectableImages } from '@/services/images'
import { createTrainingJob, createTrainingJobFromEnvironment } from '@/services/training-jobs'
import { getDevEnvironment } from '@/services/dev-environments'
import { getExperiment } from '@/services/experiments'
import { getBusinessConfigs } from '@/services/business-configs'

interface FormValues {
  name: string
  description?: string
  datasetId?: string
  datasetVersionId?: string
  imageId: string
  command: string
  useGpu: boolean
  gpuMode: string
  gpuCount: number
  cpu: string
  memory: string
  priority: string
  workerCount: number
  mlflowEnabled?: boolean
  tensorboardEnabled?: boolean
  hyperparameters?: { key: string; value: string }[]
  envVars?: { key: string; value: string }[]
}

const PRIORITY_OPTIONS = [
  { label: '低', value: 'low' },
  { label: '普通', value: 'normal' },
  { label: '高', value: 'high' },
]

const PRIORITY_TAG_COLOR: Record<string, string> = {
  low: 'blue',
  normal: 'green',
  high: 'red',
}

const MEMORY_OPTIONS = [
  { label: '4 Gi', value: '4Gi' },
  { label: '8 Gi', value: '8Gi' },
  { label: '16 Gi', value: '16Gi' },
  { label: '32 Gi', value: '32Gi' },
  { label: '64 Gi', value: '64Gi' },
  { label: '128 Gi', value: '128Gi' },
]

export default function CreateTrainingJobPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [current, setCurrent] = useState(0)
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)
  const { token } = theme.useToken()

  const fromExperimentId = searchParams.get('from_experiment')
  const [sourceExperimentId, setSourceExperimentId] = useState<string | undefined>(undefined)
  const fromEnvironmentId = searchParams.get('from_environment')

  const datasetId = Form.useWatch('datasetId', form)
  const useGpu = Form.useWatch('useGpu', form) ?? true
  const workerCount = Form.useWatch('workerCount', form) ?? 1

  const { data: datasetsData } = useQuery({
    queryKey: ['datasets-for-training', 1, 100],
    queryFn: () => getDatasets({ current: 1, pageSize: 100 }),
  })

  const { data: datasetDetail } = useQuery({
    queryKey: ['dataset-detail', datasetId],
    queryFn: () => getDatasetDetail(datasetId!),
    enabled: !!datasetId,
  })

  const { data: imagesData } = useQuery({
    queryKey: ['selectableImages'],
    queryFn: () => getSelectableImages(),
  })

  const datasets = datasetsData?.items ?? []
  const versions = datasetDetail?.versions ?? []
  const images = imagesData ?? []

  const { data: configsData } = useQuery({
    queryKey: ['business-configs-list', 1, 100],
    queryFn: () => getBusinessConfigs({ current: 1, pageSize: 100 }),
  })
  const configs = configsData?.items ?? []

  const { data: experimentDetail } = useQuery({
    queryKey: ['experiment-reproduce', fromExperimentId],
    queryFn: () => getExperiment(fromExperimentId!),
    enabled: !!fromExperimentId,
  })

  const { data: envDetail } = useQuery({
    queryKey: ['dev-environment-for-training', fromEnvironmentId],
    queryFn: () => getDevEnvironment(fromEnvironmentId!),
    enabled: !!fromEnvironmentId,
  })

  useEffect(() => {
    if (!envDetail || !fromEnvironmentId) return
    const firstMount = envDetail.mountedDatasets?.[0]
    // 环境名符合任务名规则时预填「{环境名}-train」, 中文等不合规名称留空待用户填写
    const namePrefill = /^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(envDetail.name)
      ? `${envDetail.name}-train`
      : undefined
    const envVarEntries = envDetail.envVars
      ? Object.entries(envDetail.envVars).map(([key, value]) => ({ key, value }))
      : []
    form.setFieldsValue({
      name: namePrefill,
      description: `来自开发环境「${envDetail.name}」`,
      datasetId: firstMount?.datasetId,
      datasetVersionId: firstMount?.versionId,
      useGpu: envDetail.gpuCount > 0,
      gpuCount: envDetail.gpuCount > 0 ? envDetail.gpuCount : 1,
      cpu: envDetail.cpu,
      memory: envDetail.memory,
      envVars: envVarEntries.length > 0 ? envVarEntries : undefined,
    })
  }, [envDetail, fromEnvironmentId, form])

  useEffect(() => {
    if (!experimentDetail || !fromExperimentId) return
    const job = experimentDetail.trainingJob
    setSourceExperimentId(fromExperimentId)
    const hyperParams = experimentDetail.hyperparameters
      ? Object.entries(experimentDetail.hyperparameters).map(([key, value]) => ({ key, value }))
      : []
    const gpuCount = job?.gpuCount ?? 1
    const values: Partial<FormValues> = {
      name: job?.name ? `${job.name}-reproduce` : '',
      command: job?.command ?? undefined,
      datasetId: job?.datasetId ?? undefined,
      datasetVersionId: job?.datasetVersionId ?? undefined,
      imageId: job?.imageId ?? undefined,
      useGpu: gpuCount > 0,
      gpuCount: gpuCount > 0 ? gpuCount : 1,
      gpuMode: job?.gpuMode ?? undefined,
      cpu: job?.cpu ?? undefined,
      memory: job?.memory ?? undefined,
      priority: job?.priority ?? undefined,
      workerCount: job?.workerCount ?? undefined,
      mlflowEnabled: job?.mlflowEnabled ?? false,
      tensorboardEnabled: job?.tensorboardEnabled ?? false,
      hyperparameters: hyperParams.length > 0 ? hyperParams : undefined,
      envVars: job?.envVars
        ? Object.entries(job.envVars).map(([key, value]) => ({ key, value }))
        : undefined,
    }
    form.setFieldsValue(values)
  }, [experimentDetail, fromExperimentId, form])

  // Collapse 面板惰性挂载, 未展开面板里的 Form.List 值会被 validateFields 丢弃,
  // 因此预填了超参数/环境变量时须展开对应面板使其挂载 (key 变化触发重挂载)
  const prefilledCollapseKeys: string[] = []
  if (envDetail?.envVars && Object.keys(envDetail.envVars).length > 0) {
    prefilledCollapseKeys.push('envVars')
  }
  if (experimentDetail) {
    if (
      experimentDetail.hyperparameters &&
      Object.keys(experimentDetail.hyperparameters).length > 0
    ) {
      prefilledCollapseKeys.push('hyperparams')
    }
    if (
      experimentDetail.trainingJob?.envVars &&
      Object.keys(experimentDetail.trainingJob.envVars).length > 0
    ) {
      prefilledCollapseKeys.push('envVars')
    }
  }

  const handleNext = async () => {
    try {
      if (current === 0) {
        await form.validateFields(['name', 'imageId', 'command'])
      } else {
        const fields = ['cpu', 'memory']
        if (useGpu) fields.push('gpuCount')
        await form.validateFields(fields)
      }
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
      const gpuEnabled = values.useGpu ?? true
      const envVars = values.envVars?.reduce(
        (acc: Record<string, string>, item) => {
          const key = item.key?.trim()
          if (key) acc[key] = item.value ?? ''
          return acc
        },
        {} as Record<string, string>,
      )
      const commonPayload = {
        name: values.name,
        description: values.description,
        datasetId: values.datasetId,
        datasetVersionId: values.datasetVersionId,
        command: values.command,
        hyperparameters: values.hyperparameters?.filter((h) => h?.key && h?.value),
        envVars: envVars && Object.keys(envVars).length > 0 ? envVars : undefined,
        gpuCount: gpuEnabled ? values.gpuCount : 0,
        gpuMode: gpuEnabled ? values.gpuMode : undefined,
        cpu: String(values.cpu),
        memory: values.memory,
        priority: values.priority,
        workerCount: values.workerCount,
        mlflowEnabled: values.mlflowEnabled ?? false,
        tensorboardEnabled: values.tensorboardEnabled ?? false,
      }
      const res = fromEnvironmentId
        ? await createTrainingJobFromEnvironment({
            ...commonPayload,
            environmentId: fromEnvironmentId,
            imageId: values.imageId || undefined,
          })
        : await createTrainingJob({
            ...commonPayload,
            imageId: values.imageId,
            sourceExperimentId,
          })
      getMessageInstance()?.success('训练任务创建成功')
      navigate(`/training-jobs/${res.id}`)
    } catch {
      // error handled by interceptor
    } finally {
      setSubmitting(false)
    }
  }

  const steps = [
    {
      title: '基础配置',
      icon: <FileTextOutlined />,
      content: (
        <>
          <Form.Item
            name="name"
            label="任务名称"
            rules={[
              { required: true, message: '请输入任务名称' },
              {
                pattern: /^[a-z0-9][a-z0-9-]*[a-z0-9]$/,
                message: '仅支持小写字母、数字和中划线，且以字母或数字开头',
              },
            ]}
          >
            <Input placeholder="如 my-training-job" maxLength={100} showCount />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="任务描述（可选）" rows={2} />
          </Form.Item>
          <Divider>数据与镜像</Divider>
          <Form.Item name="datasetId" label="数据集">
            <Select
              placeholder="请选择数据集（可选）"
              allowClear
              showSearch
              optionFilterProp="label"
              options={datasets.map((d) => ({ label: d.name, value: d.id }))}
            />
          </Form.Item>
          <Form.Item name="datasetVersionId" label="数据集版本">
            <Select
              placeholder={datasetId ? '默认使用最新版本' : '请先选择数据集'}
              allowClear
              options={versions.map((v) => ({
                label: `v${v.versionNumber}`,
                value: v.id,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="imageId"
            label="镜像"
            rules={fromEnvironmentId ? [] : [{ required: true, message: '请选择镜像' }]}
            extra={
              fromEnvironmentId
                ? envDetail
                  ? `留空则使用环境当前镜像 ${envDetail.image}`
                  : '留空则使用开发环境当前镜像'
                : undefined
            }
          >
            <ImageSelect
              placeholder={fromEnvironmentId ? '默认使用开发环境镜像（可留空）' : '请选择训练镜像'}
              category="training"
            />
          </Form.Item>
          <Form.Item
            name="command"
            label="启动命令"
            rules={[{ required: true, message: '请输入启动命令' }]}
            extra="默认工作目录为用户 home 目录（/kubeai/home），可访问 /kubeai/home（用户目录）、/kubeai/workspace（工作区）、/kubeai/datasets（挂载的数据集），与开发环境挂载映射一致"
          >
            <Input.TextArea
              placeholder="如 cd pytorch-mnist && python3 train.py"
              rows={4}
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
        </>
      ),
    },
    {
      title: '资源与参数',
      icon: <RocketOutlined />,
      content: (
        <>
          <Divider orientation="left" style={{ fontSize: 14 }}>
            GPU 配置
          </Divider>
          <Form.Item name="useGpu" label="启用 GPU" valuePropName="checked" initialValue={true}>
            <Switch checkedChildren="开" unCheckedChildren="关" />
          </Form.Item>
          {useGpu ? (
            <>
              <Form.Item name="gpuMode" label="GPU 模式" initialValue="exclusive">
                <Radio.Group>
                  <Radio.Button value="exclusive">独占</Radio.Button>
                  <Radio.Button value="shared">共享</Radio.Button>
                </Radio.Group>
              </Form.Item>
              <Form.Item
                name="gpuCount"
                label="GPU 数量"
                initialValue={1}
                rules={[{ required: true }]}
              >
                <InputNumber min={1} max={16} style={{ width: '100%' }} />
              </Form.Item>
            </>
          ) : (
            <Alert
              type="info"
              showIcon
              message="将创建纯 CPU 训练任务，不分配 GPU 资源"
              style={{ marginBottom: 24 }}
            />
          )}

          <Divider orientation="left" style={{ fontSize: 14 }}>
            计算资源
          </Divider>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item
              name="cpu"
              label="CPU（核）"
              initialValue="4"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <InputNumber min={1} max={128} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="memory"
              label="内存"
              initialValue="8Gi"
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <Select options={MEMORY_OPTIONS} />
            </Form.Item>
          </div>

          <Divider orientation="left" style={{ fontSize: 14 }}>
            调度配置
          </Divider>
          <Form.Item
            name="workerCount"
            label="Worker 数量"
            initialValue={1}
            rules={[{ required: true }]}
          >
            <InputNumber min={1} max={16} style={{ width: '100%' }} />
          </Form.Item>
          {workerCount > 1 && (
            <Alert
              type="info"
              showIcon
              message="分布式训练模式"
              description={`将创建 ${workerCount} 个 Worker，通过 Volcano Gang Scheduling 确保同时启动。自动注入 MASTER_ADDR、MASTER_PORT、WORLD_SIZE、RANK 环境变量，适用于 PyTorch DDP、DeepSpeed、Horovod 等分布式框架。`}
              style={{ marginBottom: 24 }}
            />
          )}
          <Form.Item name="priority" label="优先级" initialValue="normal">
            <Select options={PRIORITY_OPTIONS} />
          </Form.Item>

          <Collapse
            ghost
            key={prefilledCollapseKeys.join('|')}
            defaultActiveKey={prefilledCollapseKeys}
            items={[
              {
                key: 'hyperparams',
                label: (
                  <Space size={4}>
                    初始超参数
                    <Tooltip title="这些参数将作为环境变量原样注入容器（如 learning_rate=0.001），键名和值均不做修改。训练脚本可通过 os.environ 读取，通常用于 mlflow.log_params()。实际记录的超参数请查看实验追踪。">
                      <InfoCircleOutlined style={{ color: token.colorTextTertiary }} />
                    </Tooltip>
                  </Space>
                ),
                children: (
                  <Form.List name="hyperparameters">
                    {(fields, { add, remove }) => (
                      <>
                        {fields.map(({ key, name, ...restField }) => (
                          <Space
                            key={key}
                            style={{ display: 'flex', marginBottom: 8 }}
                            align="start"
                          >
                            <Form.Item
                              {...restField}
                              name={[name, 'key']}
                              style={{ marginBottom: 0 }}
                            >
                              <Input placeholder="参数名" />
                            </Form.Item>
                            <Form.Item
                              {...restField}
                              name={[name, 'value']}
                              style={{ marginBottom: 0 }}
                            >
                              <Input placeholder="参数值" />
                            </Form.Item>
                            <Button
                              type="text"
                              danger
                              icon={<DeleteOutlined />}
                              onClick={() => remove(name)}
                              aria-label="删除"
                            />
                          </Space>
                        ))}
                        <Button type="dashed" onClick={() => add({})} block icon={<PlusOutlined />}>
                          添加超参数
                        </Button>
                      </>
                    )}
                  </Form.List>
                ),
              },
              {
                key: 'envVars',
                label: (
                  <Space size={4}>
                    环境变量
                    <Tooltip title="通用的容器环境变量（非超参数），可用于传递 API Key、服务地址等配置。支持从业务配置预设中快速加载。">
                      <InfoCircleOutlined style={{ color: token.colorTextTertiary }} />
                    </Tooltip>
                  </Space>
                ),
                children: (
                  <Form.Item>
                    <EnvVarEditor presets={configs} />
                  </Form.Item>
                ),
              },
              {
                key: 'advanced',
                label: '高级配置',
                children: (
                  <>
                    <Form.Item
                      name="mlflowEnabled"
                      label="实验追踪 (MLflow)"
                      valuePropName="checked"
                      initialValue={false}
                      tooltip="开启后平台预创建 MLflow 实验与运行, 并把 run_id 注入环境变量 MLFLOW_RUN_ID; 训练脚本须 mlflow.start_run(run_id=...) 恢复它, 指标才能与任务绑定. 不需要指标追踪的简单任务无需开启 (默认关闭)."
                    >
                      <Switch checkedChildren="开" unCheckedChildren="关" />
                    </Form.Item>
                    <Form.Item
                      shouldUpdate={(prev, cur) => prev.mlflowEnabled !== cur.mlflowEnabled}
                      noStyle
                    >
                      {({ getFieldValue }: FormInstance) =>
                        getFieldValue('mlflowEnabled') ? (
                          <Alert
                            type="info"
                            showIcon
                            style={{ marginBottom: 24 }}
                            message="训练脚本须通过环境变量 MLFLOW_RUN_ID 恢复平台预创建的运行，否则指标无法与任务绑定"
                            description={
                              <code style={{ fontSize: 12 }}>
                                mlflow.start_run(run_id=os.environ['MLFLOW_RUN_ID'])
                              </code>
                            }
                          />
                        ) : null
                      }
                    </Form.Item>
                    <Form.Item
                      name="tensorboardEnabled"
                      label="TensorBoard 可视化"
                      valuePropName="checked"
                      initialValue={false}
                      tooltip="开启后平台自动注入 TensorBoard sidecar 容器, 训练时可在详情页实时查看 tfevents 曲线. 训练脚本需将日志写入环境变量 TENSORBOARD_LOG_DIR 指向的目录 (默认 /kubeai/tensorboard). 与 MLflow 可同时开启."
                    >
                      <Switch checkedChildren="开" unCheckedChildren="关" />
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
        </>
      ),
    },
    {
      title: '确认提交',
      icon: <CheckCircleOutlined />,
      content: (
        <ConfirmStep
          form={form}
          datasets={datasets}
          images={images}
          envImage={fromEnvironmentId ? envDetail?.image : undefined}
        />
      ),
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      {fromExperimentId &&
        experimentDetail &&
        (experimentDetail.trainingJob ? (
          <Alert
            type="info"
            showIcon
            message={`正在基于实验「${experimentDetail.trainingJobName ?? '未知'}」的配置创建新训练任务，你可以修改任意参数后提交`}
            style={{ marginBottom: 16 }}
            closable
          />
        ) : (
          <Alert
            type="warning"
            showIcon
            message="原始训练任务信息不可用，请手动填写配置"
            style={{ marginBottom: 16 }}
            closable
          />
        ))}
      {fromEnvironmentId &&
        envDetail &&
        (envDetail.status === 'running' ? (
          <Alert
            type="info"
            showIcon
            message={`正在从开发环境「${envDetail.name}」发起训练，数据集与资源配置已按环境预填，可修改后提交`}
            style={{ marginBottom: 16 }}
            closable
          />
        ) : (
          <Alert
            type="warning"
            showIcon
            message={`开发环境「${envDetail.name}」当前未在运行中，请先在开发环境页面启动后再提交`}
            style={{ marginBottom: 16 }}
            closable
          />
        ))}
      <Steps
        current={current}
        items={steps.map((s) => ({ title: s.title, icon: s.icon }))}
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
              <Button
                type="primary"
                loading={submitting}
                disabled={
                  !!fromEnvironmentId && envDetail !== undefined && envDetail.status !== 'running'
                }
                onClick={handleSubmit}
              >
                提交任务
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
  datasets,
  images,
  envImage,
}: {
  form: FormInstance<FormValues>
  datasets: { id: string; name: string }[]
  images: { id: string; name: string; tag: string }[]
  envImage?: string
}) {
  const values = Form.useWatch<FormValues>([], form)
  if (!values) return null

  const datasetName = values.datasetId
    ? (datasets.find((d) => d.id === values.datasetId)?.name ?? '—')
    : '未选择'
  const image = values.imageId ? images.find((i) => i.id === values.imageId) : null
  const imageLabel = image ? (
    `${image.name}:${image.tag}`
  ) : envImage ? (
    <Space size={4}>
      <span>{envImage}</span>
      <Tag color="blue">继承自开发环境</Tag>
    </Space>
  ) : (
    '未选择'
  )
  const hp = values.hyperparameters?.filter((h) => h?.key && h?.value) ?? []
  const ev = values.envVars?.filter((e) => e?.key?.trim()) ?? []
  const gpuEnabled = values.useGpu ?? true

  return (
    <Descriptions column={2} bordered size="small">
      <Descriptions.Item label="任务名称">{values.name}</Descriptions.Item>
      <Descriptions.Item label="描述">{values.description || '—'}</Descriptions.Item>
      <Descriptions.Item label="数据集">{datasetName}</Descriptions.Item>
      <Descriptions.Item label="数据集版本">
        {values.datasetId ? (values.datasetVersionId ? values.datasetVersionId : '最新版本') : '—'}
      </Descriptions.Item>
      <Descriptions.Item label="镜像">{imageLabel}</Descriptions.Item>
      <Descriptions.Item label="GPU">
        {gpuEnabled ? (
          <Space>
            <span>{values.gpuCount ?? 0} 张</span>
            <Tag color="blue">{values.gpuMode === 'exclusive' ? '独占' : '共享'}</Tag>
          </Space>
        ) : (
          <Tag>未启用</Tag>
        )}
      </Descriptions.Item>
      <Descriptions.Item label="Worker 数量">
        {values.workerCount ?? 1}
        {(values.workerCount ?? 1) > 1 && (
          <Tag color="blue" style={{ marginLeft: 8 }}>
            分布式训练
          </Tag>
        )}
      </Descriptions.Item>
      <Descriptions.Item label="CPU">{values.cpu} 核</Descriptions.Item>
      <Descriptions.Item label="内存">{values.memory}</Descriptions.Item>
      <Descriptions.Item label="优先级">
        <Tag color={PRIORITY_TAG_COLOR[values.priority ?? 'normal'] ?? 'green'}>
          {PRIORITY_OPTIONS.find((p) => p.value === values.priority)?.label ?? '普通'}
        </Tag>
      </Descriptions.Item>
      <Descriptions.Item label="启动命令" span={2}>
        <code
          style={{
            fontSize: 12,
            padding: '2px 6px',
            background: 'rgba(0, 0, 0, 0.04)',
            borderRadius: 4,
            wordBreak: 'break-all',
          }}
        >
          {values.command || '—'}
        </code>
      </Descriptions.Item>
      {hp.length > 0 && (
        <Descriptions.Item label="初始超参数" span={2}>
          {hp.map((h) => (
            <Tag key={h.key} style={{ marginBottom: 4 }}>
              {h.key}={h.value}
            </Tag>
          ))}
        </Descriptions.Item>
      )}
      {ev.length > 0 && (
        <Descriptions.Item label="环境变量" span={2}>
          {ev.map((e) => (
            <Tag key={e.key} style={{ marginBottom: 4 }}>
              {e.key}={e.value}
            </Tag>
          ))}
        </Descriptions.Item>
      )}
    </Descriptions>
  )
}
