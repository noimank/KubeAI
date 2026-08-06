import { useState } from 'react'
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
} from 'antd'
import {
  CheckCircleOutlined,
  FileTextOutlined,
  InfoCircleOutlined,
  RocketOutlined,
} from '@ant-design/icons'
import type { FormInstance } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import ImageSelect from '@/components/ImageSelect'
import ResourceAwarePanel from '@/components/ResourceAwarePanel'
import EnvVarEditor from '@/components/EnvVarEditor'
import SearchSpaceEditor, { type SearchSpaceRowValue } from '@/components/SearchSpaceEditor'
import { getDatasets, getDatasetDetail } from '@/services/datasets'
import { getSelectableImages } from '@/services/images'
import { getBusinessConfigs } from '@/services/business-configs'
import { createTuningStudy } from '@/services/tuning'
import type { SearchSpaceItem, TuningDirection } from '@/types/tuning'

interface FormValues {
  name: string
  description?: string
  direction: TuningDirection
  metricName: string
  nTrials: number
  nJobs: number
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
  searchSpace?: SearchSpaceRowValue[]
  envVars?: { key: string; value: string }[]
  pruningEnabled?: boolean
  pruningConfig?: {
    nStartupTrials?: number
    nWarmupSteps?: number
    interval?: number
    nMinTrials?: number
  }
}

const PRIORITY_OPTIONS = [
  { label: '低', value: 'low' },
  { label: '普通', value: 'normal' },
  { label: '高', value: 'high' },
]

const MEMORY_OPTIONS = [
  { label: '4 Gi', value: '4Gi' },
  { label: '8 Gi', value: '8Gi' },
  { label: '16 Gi', value: '16Gi' },
  { label: '32 Gi', value: '32Gi' },
  { label: '64 Gi', value: '64Gi' },
  { label: '128 Gi', value: '128Gi' },
]

/** 编辑器行值 (choices 为逗号分隔字符串) → 后端 SearchSpaceItem */
function toSearchSpaceDict(rows: SearchSpaceRowValue[]): Record<string, SearchSpaceItem> {
  const result: Record<string, SearchSpaceItem> = {}
  for (const row of rows) {
    const name = row.name?.trim()
    if (!name) continue
    const item: SearchSpaceItem = { type: row.type ?? 'float' }
    if (item.type === 'float' || item.type === 'int') {
      if (row.low !== undefined) item.low = row.low
      if (row.high !== undefined) item.high = row.high
      item.log = row.log ?? false
    } else if (item.type === 'categorical') {
      item.choices = (row.choices ?? '')
        .split(',')
        .map((c) => c.trim())
        .filter(Boolean)
    } else {
      item.value = row.value
    }
    result[name] = item
  }
  return result
}

export default function CreateTuningPage() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState(0)
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)

  const datasetId = Form.useWatch('datasetId', form)
  const useGpu = Form.useWatch('useGpu', form) ?? true
  const workerCount = Form.useWatch('workerCount', form) ?? 1

  /** searchSpace 由 Form.List 直接管理 (无独立 Form.Item 字段), 提交/下一步前手动校验至少一个有效参数. */
  const hasValidSearchSpace = (): boolean => {
    const rows: SearchSpaceRowValue[] = form.getFieldValue('searchSpace') ?? []
    if (rows.some((r) => r?.name?.trim())) return true
    getMessageInstance()?.warning('请至少定义一个超参数')
    return false
  }

  const { data: datasetsData } = useQuery({
    queryKey: ['datasets-for-tuning', 1, 100],
    queryFn: () => getDatasets({ current: 1, pageSize: 100 }),
  })
  const { data: datasetDetail } = useQuery({
    queryKey: ['dataset-detail-tuning', datasetId],
    queryFn: () => getDatasetDetail(datasetId!),
    enabled: !!datasetId,
  })
  const { data: imagesData } = useQuery({
    queryKey: ['selectableImages-tuning'],
    queryFn: () => getSelectableImages(),
  })
  const { data: configsData } = useQuery({
    queryKey: ['business-configs-for-tuning', 1, 100],
    queryFn: () => getBusinessConfigs({ current: 1, pageSize: 100 }),
  })

  const datasets = datasetsData?.items ?? []
  const versions = datasetDetail?.versions ?? []
  const images = imagesData ?? []
  const configs = configsData?.items ?? []

  const handleNext = async () => {
    try {
      if (current === 0) {
        await form.validateFields(['name', 'metricName', 'imageId', 'command'])
      } else {
        const fields = ['cpu', 'memory']
        if (useGpu) fields.push('gpuCount')
        await form.validateFields(fields)
        if (!hasValidSearchSpace()) return
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
      if (!hasValidSearchSpace()) return
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
      const searchSpace = toSearchSpaceDict(values.searchSpace ?? [])
      await createTuningStudy({
        name: values.name,
        description: values.description,
        direction: values.direction,
        metricName: values.metricName,
        nTrials: values.nTrials,
        nJobs: values.nJobs,
        searchSpace,
        datasetId: values.datasetId,
        datasetVersionId: values.datasetVersionId,
        imageId: values.imageId,
        command: values.command,
        gpuCount: gpuEnabled ? values.gpuCount : 0,
        gpuMode: gpuEnabled ? values.gpuMode : undefined,
        cpu: String(values.cpu),
        memory: values.memory,
        priority: values.priority,
        workerCount: values.workerCount,
        envVars: envVars && Object.keys(envVars).length > 0 ? envVars : undefined,
        pruningEnabled: values.pruningEnabled ?? false,
        pruningConfig: values.pruningEnabled ? values.pruningConfig : undefined,
      })
      getMessageInstance()?.success('调优任务创建成功')
      navigate('/tuning')
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
            <Input placeholder="如 lr-search" maxLength={100} showCount />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="任务描述（可选）" rows={2} />
          </Form.Item>
          <Divider>调优目标</Divider>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item
              name="direction"
              label="优化方向"
              initialValue="minimize"
              style={{ flex: 1 }}
            >
              <Select
                options={[
                  { label: '最小化 (minimize)', value: 'minimize' },
                  { label: '最大化 (maximize)', value: 'maximize' },
                ]}
              />
            </Form.Item>
            <Form.Item
              name="metricName"
              label="目标指标"
              rules={[{ required: true, message: '请输入目标指标名' }]}
              extra="训练脚本写入 MLflow 的指标键名"
              style={{ flex: 1 }}
            >
              <Input placeholder="如 val_loss" />
            </Form.Item>
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item
              name="nTrials"
              label="试验总数"
              initialValue={10}
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <InputNumber min={1} max={1000} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              name="nJobs"
              label="并发试验数"
              initialValue={1}
              rules={[{ required: true }]}
              tooltip="同时运行的最大 trial 数量，受租户 GPU 配额约束"
              style={{ flex: 1 }}
            >
              <InputNumber min={1} max={16} style={{ width: '100%' }} />
            </Form.Item>
          </div>
          <Collapse
            ghost
            items={[
              {
                key: 'pruning',
                label: (
                  <Space size={4}>
                    剪枝 (Pruning)
                    <Tooltip title="启用后, 表现持续差于已完成 trial 中位数的 trial 会被提前终止以节省算力。要求训练脚本对目标指标按 step 上报到 MLflow (mlflow.log_metric(name, value, step=...))。">
                      <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                  </Space>
                ),
                children: (
                  <>
                    <Form.Item
                      name="pruningEnabled"
                      label="启用剪枝"
                      valuePropName="checked"
                      initialValue={false}
                    >
                      <Switch checkedChildren="开" unCheckedChildren="关" />
                    </Form.Item>
                    <Form.Item
                      noStyle
                      shouldUpdate={(prev, cur) => prev.pruningEnabled !== cur.pruningEnabled}
                    >
                      {({ getFieldValue }) =>
                        getFieldValue('pruningEnabled') ? (
                          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                            <Form.Item
                              name={['pruningConfig', 'nStartupTrials']}
                              label="启动试验数"
                              initialValue={5}
                              tooltip="前 N 个 trial 不剪枝, 用于积累参考分布"
                              style={{ flex: '1 1 200px' }}
                            >
                              <InputNumber min={0} style={{ width: '100%' }} />
                            </Form.Item>
                            <Form.Item
                              name={['pruningConfig', 'nWarmupSteps']}
                              label="预热步数"
                              initialValue={3}
                              tooltip="每个 trial 前 N 步不评估"
                              style={{ flex: '1 1 200px' }}
                            >
                              <InputNumber min={0} style={{ width: '100%' }} />
                            </Form.Item>
                            <Form.Item
                              name={['pruningConfig', 'interval']}
                              label="评估间隔"
                              initialValue={1}
                              tooltip="每 N 步评估一次是否剪枝"
                              style={{ flex: '1 1 200px' }}
                            >
                              <InputNumber min={1} style={{ width: '100%' }} />
                            </Form.Item>
                            <Form.Item
                              name={['pruningConfig', 'nMinTrials']}
                              label="最少参考数"
                              initialValue={3}
                              tooltip="已完成 trial 不足此数时不判定"
                              style={{ flex: '1 1 200px' }}
                            >
                              <InputNumber min={1} style={{ width: '100%' }} />
                            </Form.Item>
                          </div>
                        ) : null
                      }
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
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
              options={versions.map((v) => ({ label: `v${v.versionNumber}`, value: v.id }))}
            />
          </Form.Item>
          <Form.Item
            name="imageId"
            label="镜像"
            rules={[{ required: true, message: '请选择镜像' }]}
          >
            <ImageSelect placeholder="请选择训练镜像" category="training" />
          </Form.Item>
          <Form.Item
            name="command"
            label="启动命令"
            rules={[{ required: true, message: '请输入启动命令' }]}
            extra="每个 trial 都会以该命令启动，采样到的超参数作为环境变量注入；训练脚本须把目标指标写入 MLflow（指标键名对应上方目标指标）"
          >
            <Input.TextArea
              placeholder="如 python3 train.py --epochs 20"
              rows={4}
              style={{ fontFamily: 'monospace' }}
            />
          </Form.Item>
        </>
      ),
    },
    {
      title: '资源与搜索空间',
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
              message="将创建纯 CPU 调优任务"
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
          <div style={{ display: 'flex', gap: 16 }}>
            <Form.Item
              name="workerCount"
              label="Worker 数量"
              initialValue={1}
              rules={[{ required: true }]}
              style={{ flex: 1 }}
            >
              <InputNumber min={1} max={16} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="priority" label="优先级" initialValue="normal" style={{ flex: 1 }}>
              <Select options={PRIORITY_OPTIONS} />
            </Form.Item>
          </div>
          {workerCount > 1 && (
            <Alert
              type="info"
              showIcon
              message="分布式训练模式"
              description={`每个 trial 将以 ${workerCount} 个 Worker 运行，自动注入 MASTER_ADDR、MASTER_PORT、WORLD_SIZE、RANK 环境变量。`}
              style={{ marginBottom: 24 }}
            />
          )}

          <Divider orientation="left" style={{ fontSize: 14 }}>
            搜索空间
          </Divider>
          <Form.Item label="搜索空间" required>
            <SearchSpaceEditor name="searchSpace" />
          </Form.Item>

          <Collapse
            ghost
            items={[
              {
                key: 'envVars',
                label: (
                  <Space size={4}>
                    附加环境变量
                    <Tooltip title="附加到每个 trial 的通用环境变量（非超参数），可用于传递 API Key、服务地址等配置。支持从业务配置预设中快速加载。">
                      <InfoCircleOutlined style={{ color: '#999' }} />
                    </Tooltip>
                  </Space>
                ),
                children: (
                  <Form.Item>
                    <EnvVarEditor
                      name="envVars"
                      keyPlaceholder="变量名"
                      valuePlaceholder="变量值"
                      addButtonText="+ 添加环境变量"
                      presets={configs}
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
      <Alert
        type="info"
        showIcon
        message="调优任务创建后由平台调度器自动采样并逐个提交 trial 训练任务；训练脚本无需依赖 Optuna，只需把目标指标写入 MLflow。"
        style={{ marginBottom: 16 }}
      />
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
  const gpuEnabled = values.useGpu ?? true
  const searchSpace = toSearchSpaceDict(values.searchSpace ?? [])
  const ev = values.envVars?.filter((e) => e?.key?.trim()) ?? []

  return (
    <Descriptions column={2} bordered size="small">
      <Descriptions.Item label="任务名称">{values.name}</Descriptions.Item>
      <Descriptions.Item label="描述">{values.description || '—'}</Descriptions.Item>
      <Descriptions.Item label="优化方向">
        <Tag color={values.direction === 'minimize' ? 'blue' : 'orange'}>
          {values.direction === 'minimize' ? '最小化' : '最大化'}
        </Tag>
      </Descriptions.Item>
      <Descriptions.Item label="目标指标">{values.metricName}</Descriptions.Item>
      <Descriptions.Item label="试验总数">{values.nTrials}</Descriptions.Item>
      <Descriptions.Item label="并发试验数">{values.nJobs}</Descriptions.Item>
      <Descriptions.Item label="剪枝">
        {values.pruningEnabled ? <Tag color="green">启用</Tag> : <Tag>未启用</Tag>}
      </Descriptions.Item>
      <Descriptions.Item label="数据集">{datasetName}</Descriptions.Item>
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
      <Descriptions.Item label="Worker 数量">{values.workerCount ?? 1}</Descriptions.Item>
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
      <Descriptions.Item label="搜索空间" span={2}>
        {Object.entries(searchSpace).map(([k, v]) => (
          <Tag key={k} style={{ marginBottom: 4 }}>
            {k}: {JSON.stringify(v)}
          </Tag>
        ))}
      </Descriptions.Item>
      {ev.length > 0 && (
        <Descriptions.Item label="附加环境变量" span={2}>
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
