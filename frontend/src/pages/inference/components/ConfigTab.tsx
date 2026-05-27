import { useState } from 'react'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Form,
  InputNumber,
  Modal,
  Popover,
  Select,
  Space,
  Switch,
  Tag,
  Typography,
} from 'antd'
import { ThunderboltOutlined } from '@ant-design/icons'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { scaleInferenceService, updateAutoScaling } from '@/services/inference'
import { useResourceQuota } from '@/hooks/useResourceQuota'
import type { AutoScalingUpdateRequest, InferenceService, MetricType } from '@/types/inference'

const METRIC_TYPE_OPTIONS = [
  { label: '并发请求数', value: 'concurrency' },
  { label: 'CPU 利用率', value: 'cpu' },
]

interface ConfigTabProps {
  service: InferenceService
  canWrite: boolean
}

export function ConfigTab({ service: svc, canWrite }: ConfigTabProps) {
  const queryClient = useQueryClient()
  const [autoScalingModalOpen, setAutoScalingModalOpen] = useState(false)
  const [scalePopoverOpen, setScalePopoverOpen] = useState(false)
  const [scaleValue, setScaleValue] = useState(svc.replicas)

  const isAutoMode = svc.scalingMode === 'auto'
  const { quota } = useResourceQuota()

  const scaleMutation = useMutation({
    mutationFn: (replicas: number) => scaleInferenceService(svc.id, { replicas }),
    onSuccess: () => {
      getMessageInstance()?.success('副本数调整成功')
      setScalePopoverOpen(false)
      queryClient.invalidateQueries({ queryKey: ['inferenceService', svc.id] })
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      getMessageInstance()?.error(err?.response?.data?.message || '副本数调整失败')
    },
  })

  const autoScalingMutation = useMutation({
    mutationFn: (data: AutoScalingUpdateRequest) => updateAutoScaling(svc.id, data),
    onSuccess: () => {
      getMessageInstance()?.success('自动伸缩配置已更新')
      setAutoScalingModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['inferenceService', svc.id] })
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      getMessageInstance()?.error(err?.response?.data?.message || '自动伸缩配置失败')
    },
  })

  const handleScaleConfirm = () => {
    if (scaleValue === 0 && svc.replicas > 0) {
      Modal.confirm({
        title: '确认缩容到零',
        content: '确定将副本数调整为 0？服务将停止但配置保留，可随时恢复',
        okText: '确认',
        cancelText: '取消',
        onOk: () => scaleMutation.mutate(0),
      })
    } else {
      scaleMutation.mutate(scaleValue)
    }
  }

  const handleToggleAutoScaling = (checked: boolean) => {
    if (checked) {
      setAutoScalingModalOpen(true)
    } else {
      Modal.confirm({
        title: '切换为手动模式',
        content: '将删除自动伸缩配置，副本数将固定为当前值。确定继续？',
        okText: '确认切换',
        cancelText: '取消',
        onOk: () => {
          autoScalingMutation.mutate({
            scalingMode: 'fixed',
            minReplicas: svc.replicas || 1,
            maxReplicas: svc.replicas || 1,
            cooldownPeriod: 300,
            pollingInterval: 30,
          })
        },
      })
    }
  }

  const showScaleBtn = canWrite && svc.status !== 'failed' && svc.status !== 'pending'

  return (
    <>
      <AutoScalingModal
        open={autoScalingModalOpen}
        onCancel={() => setAutoScalingModalOpen(false)}
        onSubmit={(data) => autoScalingMutation.mutate(data)}
        loading={autoScalingMutation.isPending}
        gpuCount={svc.gpuCount}
        initialData={
          isAutoMode
            ? {
                minReplicas: svc.minReplicas,
                maxReplicas: svc.maxReplicas,
                targetMetricType: svc.targetMetricType,
                targetMetricValue: svc.targetMetricValue,
                cooldownPeriod: svc.cooldownPeriod,
                pollingInterval: svc.pollingInterval,
              }
            : undefined
        }
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {/* 扩缩容设置卡片 */}
        <Card size="small" title="扩缩容设置">
          {/* 伸缩模式切换 */}
          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <Space>
                <Typography.Text strong>自动伸缩</Typography.Text>
                {isAutoMode && (
                  <Tag icon={<ThunderboltOutlined />} color="blue">
                    已启用
                  </Tag>
                )}
              </Space>
              {canWrite && (
                <Switch
                  size="small"
                  checked={isAutoMode}
                  onChange={handleToggleAutoScaling}
                  disabled={svc.status === 'failed'}
                />
              )}
            </div>

            {isAutoMode && (
              <div style={{ marginTop: 12 }}>
                <Descriptions column={2} size="small">
                  <Descriptions.Item label="副本范围">
                    {svc.minReplicas} - {svc.maxReplicas}
                  </Descriptions.Item>
                  <Descriptions.Item label="当前副本">{svc.replicas}</Descriptions.Item>
                  <Descriptions.Item label="目标指标">
                    {svc.targetMetricType === 'cpu' ? 'CPU 利用率' : '并发请求数'}{' '}
                    {svc.targetMetricValue &&
                      `> ${svc.targetMetricValue}${svc.targetMetricType === 'cpu' ? '%' : ''}`}
                  </Descriptions.Item>
                  <Descriptions.Item label="冷却时间">{svc.cooldownPeriod} 秒</Descriptions.Item>
                </Descriptions>

                {isAutoMode && svc.minReplicas === 0 && svc.status === 'running' && (
                  <Alert
                    type="info"
                    message="支持缩容到零，无流量时自动释放 GPU 资源"
                    showIcon
                    style={{ marginTop: 8 }}
                  />
                )}

                {canWrite && (
                  <Button
                    size="small"
                    type="link"
                    onClick={() => setAutoScalingModalOpen(true)}
                    style={{ padding: 0, marginTop: 8 }}
                  >
                    修改配置
                  </Button>
                )}
              </div>
            )}

            {!isAutoMode && showScaleBtn && (
              <div style={{ marginTop: 12 }}>
                <Popover
                  open={scalePopoverOpen}
                  onOpenChange={(open) => {
                    setScalePopoverOpen(open)
                    if (open) setScaleValue(svc.replicas)
                  }}
                  title={svc.status === 'stopped' ? '重启服务' : '调整副本数'}
                  trigger="click"
                  content={
                    <div style={{ width: 240 }}>
                      <div style={{ marginBottom: 8 }}>
                        <span>目标副本数: </span>
                        <InputNumber
                          min={0}
                          max={100}
                          value={scaleValue}
                          onChange={(v) => setScaleValue(v ?? 0)}
                          style={{ width: 80 }}
                        />
                      </div>
                      <div style={{ marginBottom: 8, color: '#888', fontSize: 12 }}>
                        当前: {svc.replicas} → 目标: {scaleValue}
                        {svc.gpuCount > 0 && <span> | 需要 GPU: {svc.gpuCount * scaleValue}</span>}
                      </div>
                      {svc.status === 'stopped' && scaleValue > 0 && (
                        <Alert
                          type="warning"
                          message="服务已停止，调整副本数将重新启动服务"
                          style={{ marginBottom: 8, fontSize: 12 }}
                        />
                      )}
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                        <Button size="small" onClick={() => setScalePopoverOpen(false)}>
                          取消
                        </Button>
                        <Button
                          size="small"
                          type="primary"
                          loading={scaleMutation.isPending}
                          disabled={scaleValue === svc.replicas && svc.status !== 'stopped'}
                          onClick={handleScaleConfirm}
                        >
                          {svc.status === 'stopped' && scaleValue > 0 ? '确认并启动' : '确认调整'}
                        </Button>
                      </div>
                    </div>
                  }
                >
                  <Button size="small">调整副本数 ({svc.replicas})</Button>
                </Popover>

                {svc.gpuCount > 0 && quota && (
                  <Typography.Text type="secondary" style={{ marginLeft: 12, fontSize: 12 }}>
                    可用 GPU: {quota.gpu.total - quota.gpu.used} / {quota.gpu.total} 张
                  </Typography.Text>
                )}
              </div>
            )}
          </div>
        </Card>

        {/* 环境变量配置 */}
        <Card size="small" title="环境变量">
          {!svc.envVars || Object.keys(svc.envVars).length === 0 ? (
            <Typography.Text type="secondary">暂无环境变量配置</Typography.Text>
          ) : (
            <Descriptions column={1} size="small">
              {Object.entries(svc.envVars).map(([key, value]) => (
                <Descriptions.Item key={key} label={key}>
                  <Typography.Text copyable={{ text: value }}>{value}</Typography.Text>
                </Descriptions.Item>
              ))}
            </Descriptions>
          )}
        </Card>

        {/* 资源配置详情 */}
        <Card size="small" title="资源配置">
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="CPU">{svc.cpu} 核</Descriptions.Item>
            <Descriptions.Item label="内存">{svc.memory}</Descriptions.Item>
            {svc.gpuCount > 0 && (
              <Descriptions.Item label="GPU">{svc.gpuCount} 张</Descriptions.Item>
            )}
            <Descriptions.Item label="镜像">
              <Typography.Text ellipsis style={{ maxWidth: 300 }}>
                {svc.image || '—'}
              </Typography.Text>
            </Descriptions.Item>
          </Descriptions>
        </Card>
      </div>
    </>
  )
}

/* ── AutoScaling Modal ──────────────────────────────────────────────────── */

function AutoScalingModal({
  open,
  onCancel,
  onSubmit,
  loading,
  gpuCount,
  initialData,
}: {
  open: boolean
  onCancel: () => void
  onSubmit: (data: AutoScalingUpdateRequest) => void
  loading: boolean
  gpuCount: number
  initialData?: {
    minReplicas: number
    maxReplicas: number
    targetMetricType?: MetricType
    targetMetricValue?: number
    cooldownPeriod: number
    pollingInterval: number
  }
}) {
  const [form] = Form.useForm()
  const { quota } = useResourceQuota()

  const maxReplicas = Form.useWatch('maxReplicas', form) || 1

  const gpuPreview = gpuCount * maxReplicas
  const gpuAvailable = quota ? quota.gpu.total - quota.gpu.used : 0

  const handleFinish = () => {
    form.validateFields().then((values) => {
      onSubmit({
        scalingMode: 'auto',
        minReplicas: values.minReplicas,
        maxReplicas: values.maxReplicas,
        targetMetricType: values.targetMetricType,
        targetMetricValue: values.targetMetricValue,
        cooldownPeriod: values.cooldownPeriod ?? 300,
        pollingInterval: values.pollingInterval ?? 30,
      })
    })
  }

  return (
    <Modal
      open={open}
      title="自动伸缩配置"
      onCancel={onCancel}
      onOk={handleFinish}
      confirmLoading={loading}
      okText="保存配置"
      cancelText="取消"
      width={520}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          minReplicas: initialData?.minReplicas ?? 0,
          maxReplicas: initialData?.maxReplicas ?? 5,
          targetMetricType: initialData?.targetMetricType ?? 'cpu',
          targetMetricValue: initialData?.targetMetricValue ?? 70,
          cooldownPeriod: initialData?.cooldownPeriod ?? 300,
          pollingInterval: initialData?.pollingInterval ?? 30,
        }}
      >
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
                  <Form.Item name="cooldownPeriod" label="冷却时间（秒）" style={{ flex: 1 }}>
                    <InputNumber min={0} max={3600} style={{ width: '100%' }} />
                  </Form.Item>
                  <Form.Item name="pollingInterval" label="轮询间隔（秒）" style={{ flex: 1 }}>
                    <InputNumber min={5} max={300} style={{ width: '100%' }} />
                  </Form.Item>
                </div>
              ),
            },
          ]}
        />

        {gpuCount > 0 && (
          <div
            style={{ marginTop: 12, padding: '8px 12px', background: '#fafafa', borderRadius: 6 }}
          >
            <Typography.Text style={{ fontSize: 12 }}>
              GPU 预估: {gpuCount} x {maxReplicas} = {gpuPreview} 张
              {quota && (
                <span
                  style={{
                    marginLeft: 8,
                    color: gpuPreview > gpuAvailable ? '#ff4d4f' : '#52c41a',
                  }}
                >
                  (可用: {gpuAvailable} 张)
                </span>
              )}
            </Typography.Text>
          </div>
        )}
      </Form>
    </Modal>
  )
}
