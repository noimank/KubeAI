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
} from 'antd'
import { CheckCircleOutlined, FileTextOutlined, RocketOutlined } from '@ant-design/icons'
import type { FormInstance } from 'antd'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import ImageSelect from '@/components/ImageSelect'
import ResourceAwarePanel from '@/components/ResourceAwarePanel'
import { getDatasets, getDatasetDetail } from '@/services/datasets'
import { getSelectableImages } from '@/services/images'
import { createTrainingJob } from '@/services/training-jobs'
import { getExperiment } from '@/services/experiments'

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
  metricsPort?: number
  hyperparameters?: { key: string; value: string }[]
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

  const fromExperimentId = searchParams.get('from_experiment')
  const [sourceExperimentId, setSourceExperimentId] = useState<string | undefined>(undefined)

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
    queryFn: getSelectableImages,
  })

  const datasets = datasetsData?.items ?? []
  const versions = datasetDetail?.versions ?? []
  const images = imagesData ?? []

  const { data: experimentDetail } = useQuery({
    queryKey: ['experiment-reproduce', fromExperimentId],
    queryFn: () => getExperiment(fromExperimentId!),
    enabled: !!fromExperimentId,
  })

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
      metricsPort: job?.metricsPort ?? undefined,
      hyperparameters: hyperParams.length > 0 ? hyperParams : undefined,
    }
    form.setFieldsValue(values)
  }, [experimentDetail, fromExperimentId, form])

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
      const res = await createTrainingJob({
        name: values.name,
        description: values.description,
        datasetId: values.datasetId,
        datasetVersionId: values.datasetVersionId,
        imageId: values.imageId,
        command: values.command,
        hyperparameters: values.hyperparameters?.filter((h) => h?.key && h?.value),
        gpuCount: gpuEnabled ? values.gpuCount : 0,
        gpuMode: gpuEnabled ? values.gpuMode : undefined,
        cpu: String(values.cpu),
        memory: values.memory,
        priority: values.priority,
        workerCount: values.workerCount,
        metricsPort: values.metricsPort,
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
            rules={[{ required: true, message: '请选择镜像' }]}
          >
            <ImageSelect placeholder="请选择训练镜像" />
          </Form.Item>
          <Form.Item
            name="command"
            label="启动命令"
            rules={[{ required: true, message: '请输入启动命令' }]}
          >
            <Input.TextArea
              placeholder="如 python train.py --epochs 100"
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
            items={[
              {
                key: 'hyperparams',
                label: '超参数',
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
                            <Button onClick={() => remove(name)} danger>
                              删除
                            </Button>
                          </Space>
                        ))}
                        <Button type="dashed" onClick={() => add({})} block>
                          添加超参数
                        </Button>
                      </>
                    )}
                  </Form.List>
                ),
              },
              {
                key: 'advanced',
                label: '高级配置',
                children: (
                  <Form.Item
                    name="metricsPort"
                    label="指标端口"
                    extra="如训练脚本暴露 TensorBoard/MLflow 等指标面板，填写端口号"
                  >
                    <InputNumber
                      min={1}
                      max={65535}
                      placeholder="如 6006"
                      style={{ width: '100%' }}
                    />
                  </Form.Item>
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
      content: <ConfirmStep form={form} datasets={datasets} images={images} />,
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
              <Button type="primary" loading={submitting} onClick={handleSubmit}>
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
}: {
  form: FormInstance<FormValues>
  datasets: { id: string; name: string }[]
  images: { id: string; name: string; tag: string }[]
}) {
  const values = Form.useWatch<FormValues>([], form)
  if (!values) return null

  const datasetName = values.datasetId
    ? (datasets.find((d) => d.id === values.datasetId)?.name ?? '—')
    : '未选择'
  const image = values.imageId ? images.find((i) => i.id === values.imageId) : null
  const imageLabel = image ? `${image.name}:${image.tag}` : '未选择'
  const hp = values.hyperparameters?.filter((h) => h?.key && h?.value) ?? []
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
        <Descriptions.Item label="超参数" span={2}>
          {hp.map((h) => (
            <Tag key={h.key} style={{ marginBottom: 4 }}>
              {h.key}={h.value}
            </Tag>
          ))}
        </Descriptions.Item>
      )}
      {values.metricsPort && (
        <Descriptions.Item label="指标端口" span={2}>
          {values.metricsPort}
        </Descriptions.Item>
      )}
    </Descriptions>
  )
}
