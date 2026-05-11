import { useState } from 'react'
import {
  Alert,
  Button,
  Descriptions,
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
import ImageSelect from '@/components/ImageSelect'
import { getDatasets } from '@/services/datasets'
import { getDatasetDetail } from '@/services/datasets'
import { createTrainingJob } from '@/services/training-jobs'

interface FormValues {
  name: string
  description?: string
  datasetId?: string
  datasetVersionId?: string
  imageId: string
  command: string
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

export default function CreateTrainingJobPage() {
  const navigate = useNavigate()
  const [current, setCurrent] = useState(0)
  const [form] = Form.useForm<FormValues>()
  const [submitting, setSubmitting] = useState(false)

  const datasetId = Form.useWatch('datasetId', form)
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

  const datasets = datasetsData?.items ?? []
  const versions = datasetDetail?.data?.versions ?? []

  const handleNext = async () => {
    try {
      await form.validateFields(
        current === 0 ? ['name', 'imageId', 'command'] : ['gpuCount', 'cpu', 'memory'],
      )
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
      const res = await createTrainingJob({
        name: values.name,
        description: values.description,
        datasetId: values.datasetId,
        datasetVersionId: values.datasetVersionId,
        imageId: values.imageId,
        command: values.command,
        hyperparameters: values.hyperparameters?.filter((h) => h.key && h.value),
        gpuCount: values.gpuCount,
        gpuMode: values.gpuMode,
        cpu: String(values.cpu),
        memory: values.memory,
        priority: values.priority,
        workerCount: values.workerCount,
        metricsPort: values.metricsPort,
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
      content: (
        <>
          <Form.Item name="gpuMode" label="GPU 模式" initialValue="exclusive">
            <Radio.Group>
              <Radio value="exclusive">独占</Radio>
              <Radio value="shared">共享</Radio>
            </Radio.Group>
          </Form.Item>
          <Form.Item name="gpuCount" label="GPU 数量" initialValue={1} rules={[{ required: true }]}>
            <InputNumber min={0} max={16} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item
            name="workerCount"
            label="Worker 数量"
            initialValue={1}
            rules={[{ required: true }]}
            extra={workerCount > 1 ? undefined : undefined}
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
          <Form.Item name="cpu" label="CPU（核）" initialValue="4" rules={[{ required: true }]}>
            <InputNumber min={1} max={128} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="memory" label="内存" initialValue="8Gi" rules={[{ required: true }]}>
            <Select
              options={[
                { label: '4 Gi', value: '4Gi' },
                { label: '8 Gi', value: '8Gi' },
                { label: '16 Gi', value: '16Gi' },
                { label: '32 Gi', value: '32Gi' },
                { label: '64 Gi', value: '64Gi' },
                { label: '128 Gi', value: '128Gi' },
              ]}
            />
          </Form.Item>
          <Form.Item name="priority" label="优先级" initialValue="normal">
            <Select options={PRIORITY_OPTIONS} />
          </Form.Item>
          <Form.Item label="超参数">
            <Form.List name="hyperparameters">
              {(fields, { add, remove }) => (
                <>
                  {fields.map(({ key, name, ...restField }) => (
                    <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="start">
                      <Form.Item {...restField} name={[name, 'key']} style={{ marginBottom: 0 }}>
                        <Input placeholder="参数名" />
                      </Form.Item>
                      <Form.Item {...restField} name={[name, 'value']} style={{ marginBottom: 0 }}>
                        <Input placeholder="参数值" />
                      </Form.Item>
                      <Button onClick={() => remove(name)} danger>
                        删除
                      </Button>
                    </Space>
                  ))}
                  <Button type="dashed" onClick={() => add()} block>
                    添加超参数
                  </Button>
                </>
              )}
            </Form.List>
          </Form.Item>
          <Form.Item
            name="metricsPort"
            label="指标端口"
            extra="如训练脚本暴露 TensorBoard/MLflow 等指标面板，填写端口号"
          >
            <InputNumber min={1} max={65535} placeholder="如 6006" style={{ width: '100%' }} />
          </Form.Item>
        </>
      ),
    },
    {
      title: '确认提交',
      content: <ConfirmStep form={form} datasets={datasets} />,
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      <Steps
        current={current}
        items={steps.map((s) => ({ title: s.title }))}
        style={{ marginBottom: 24 }}
      />
      <Form form={form} layout="vertical" style={{ maxWidth: 640 }}>
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
  )
}

function ConfirmStep({
  form,
  datasets,
}: {
  form: FormInstance<FormValues>
  datasets: { id: string; name: string }[]
}) {
  const values = Form.useWatch<FormValues>([], form)
  if (!values) return null

  const datasetName = values.datasetId
    ? (datasets.find((d) => d.id === values.datasetId)?.name ?? '—')
    : '未选择'
  const hp = values.hyperparameters?.filter((h) => h.key && h.value) ?? []

  return (
    <Descriptions column={2} bordered size="small">
      <Descriptions.Item label="任务名称">{values.name}</Descriptions.Item>
      <Descriptions.Item label="描述">{values.description || '—'}</Descriptions.Item>
      <Descriptions.Item label="数据集">{datasetName}</Descriptions.Item>
      <Descriptions.Item label="数据集版本">
        {values.datasetId ? (values.datasetVersionId ? values.datasetVersionId : '最新版本') : '—'}
      </Descriptions.Item>
      <Descriptions.Item label="镜像">{values.imageId ? '已选择' : '未选择'}</Descriptions.Item>
      <Descriptions.Item label="GPU">
        {values.gpuCount ?? 0} 张 ({values.gpuMode === 'exclusive' ? '独占' : '共享'})
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
        {PRIORITY_OPTIONS.find((p) => p.value === values.priority)?.label ?? '普通'}
      </Descriptions.Item>
      <Descriptions.Item label="启动命令" span={2}>
        <code style={{ fontSize: 12 }}>{values.command || '—'}</code>
      </Descriptions.Item>
      {hp.length > 0 && (
        <Descriptions.Item label="超参数" span={2}>
          {hp.map((h) => `${h.key}=${h.value}`).join(', ')}
        </Descriptions.Item>
      )}
    </Descriptions>
  )
}
