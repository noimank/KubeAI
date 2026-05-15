import { useState } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Divider,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Popover,
  Progress,
  Select,
  Slider,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { ExperimentOutlined, ThunderboltOutlined, SyncOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { useResourceQuota } from '@/hooks/useResourceQuota'
import {
  getInferenceService,
  getInferenceServiceEvents,
  regenerateToken,
  scaleInferenceService,
  updateAutoScaling,
  startCanary,
  updateCanaryTraffic,
  promoteCanary,
  rollbackCanary,
  getCanaryStatus,
} from '@/services/inference'
import { getModel } from '@/services/models'
import type { AutoScalingUpdateRequest, InferenceServiceEvent, MetricType } from '@/types/inference'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'warning', text: '等待中' },
  deploying: { color: 'processing', text: '部署中' },
  running: { color: 'success', text: '运行中' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

const CANARY_STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  none: { color: 'default', text: '无金丝雀' },
  deploying: { color: 'processing', text: '部署中' },
  running: { color: 'success', text: '运行中' },
  failed: { color: 'error', text: '已失败' },
}

const METRIC_TYPE_OPTIONS = [
  { label: '并发请求数', value: 'concurrency' },
  { label: 'CPU 利用率', value: 'cpu' },
]

export default function InferenceServiceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tokenVisible, setTokenVisible] = useState(() => !!location.state?.authToken)
  const [scalePopoverOpen, setScalePopoverOpen] = useState(false)
  const [scaleValue, setScaleValue] = useState(1)
  const [autoScalingModalOpen, setAutoScalingModalOpen] = useState(false)
  const [canaryStartModalOpen, setCanaryStartModalOpen] = useState(false)
  const [canaryTrafficModalOpen, setCanaryTrafficModalOpen] = useState(false)
  const authToken = (location.state as { authToken?: string } | null)?.authToken

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('inference_services:write')
  const canManage = hasPermission('inference_services:manage')

  const { data: svc, isLoading } = useQuery({
    queryKey: ['inferenceService', id],
    queryFn: () => getInferenceService(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      const canaryStatus = query.state.data?.canaryStatus
      if (status && ['pending', 'deploying'].includes(status)) return 5000
      if (canaryStatus === 'deploying') return 5000
      return false
    },
  })

  const { data: canaryStatusData } = useQuery({
    queryKey: ['canaryStatus', id],
    queryFn: () => getCanaryStatus(id!),
    enabled: !!id && !!svc?.canaryKserveName && svc.canaryStatus !== 'none',
    refetchInterval: svc?.canaryStatus === 'deploying' ? 5000 : 30000,
  })

  const regenerateMutation = useMutation({
    mutationFn: () => regenerateToken(id!),
    onSuccess: (token: string) => {
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
      getMessageInstance()?.success('Token 已重新生成')
      Modal.info({
        title: '新的 API Token',
        content: (
          <div>
            <Alert type="warning" message="请妥善保存，仅显示一次" style={{ marginBottom: 12 }} />
            <Typography.Paragraph copyable code style={{ wordBreak: 'break-all' }}>
              {token}
            </Typography.Paragraph>
          </div>
        ),
        width: 560,
      })
    },
  })

  const scaleMutation = useMutation({
    mutationFn: (replicas: number) => scaleInferenceService(id!, { replicas }),
    onSuccess: () => {
      getMessageInstance()?.success('副本数调整成功')
      setScalePopoverOpen(false)
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      getMessageInstance()?.error(err?.response?.data?.message || '副本数调整失败')
    },
  })

  const autoScalingMutation = useMutation({
    mutationFn: (data: AutoScalingUpdateRequest) => updateAutoScaling(id!, data),
    onSuccess: () => {
      getMessageInstance()?.success('自动伸缩配置已更新')
      setAutoScalingModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      getMessageInstance()?.error(err?.response?.data?.message || '自动伸缩配置失败')
    },
  })

  const startCanaryMutation = useMutation({
    mutationFn: (data: { canaryModelVersionId: string; canaryTrafficPercent: number }) =>
      startCanary(id!, data),
    onSuccess: () => {
      getMessageInstance()?.success('金丝雀版本部署中...')
      setCanaryStartModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
      queryClient.invalidateQueries({ queryKey: ['canaryStatus', id] })
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      getMessageInstance()?.error(err?.response?.data?.message || '金丝雀启动失败')
    },
  })

  const promoteCanaryMutation = useMutation({
    mutationFn: promoteCanary,
    onSuccess: () => {
      getMessageInstance()?.success('金丝雀版本已提升为稳定版本')
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
      queryClient.invalidateQueries({ queryKey: ['canaryStatus', id] })
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      getMessageInstance()?.error(err?.response?.data?.message || '金丝雀提升失败')
    },
  })

  const rollbackCanaryMutation = useMutation({
    mutationFn: rollbackCanary,
    onSuccess: () => {
      getMessageInstance()?.success('金丝雀版本已回滚')
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
      queryClient.invalidateQueries({ queryKey: ['canaryStatus', id] })
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      getMessageInstance()?.error(err?.response?.data?.message || '金丝雀回滚失败')
    },
  })

  const updateTrafficMutation = useMutation({
    mutationFn: (data: { canaryTrafficPercent: number }) => updateCanaryTraffic(id!, data),
    onSuccess: () => {
      getMessageInstance()?.success('金丝雀流量已调整')
      setCanaryTrafficModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
      queryClient.invalidateQueries({ queryKey: ['canaryStatus', id] })
    },
    onError: (err: { response?: { data?: { message?: string } } }) => {
      getMessageInstance()?.error(err?.response?.data?.message || '流量调整失败')
    },
  })

  const { data: events = [], isLoading: eventsLoading } = useQuery({
    queryKey: ['inferenceServiceEvents', id],
    queryFn: () => getInferenceServiceEvents(id!),
    enabled: !!id && !!svc?.kserveName && svc.status !== 'pending' && svc.status !== 'stopped',
    refetchInterval: svc?.status === 'running' || svc?.status === 'deploying' ? 30000 : false,
  })

  if (isLoading) return <Spin />
  if (!svc) return null

  const statusCfg = STATUS_CONFIG[svc.status] ?? { color: 'default', text: svc.status }
  const isAutoMode = svc.scalingMode === 'auto'
  const showScaleBtn = canWrite && svc.status !== 'failed' && svc.status !== 'pending'

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

  const proxyUrl = svc.proxyEndpoint || ''
  const curlExample = proxyUrl
    ? `curl -X POST '${proxyUrl}' \\
  -H 'Authorization: Bearer sk-your-api-token' \\
  -H 'Content-Type: application/json' \\
  -d '{"instances": [[6.8, 2.8, 4.8, 1.4]]}'`
    : ''
  const pythonExample = proxyUrl
    ? `import requests

response = requests.post(
    "${proxyUrl}",
    headers={
        "Authorization": "Bearer sk-your-api-token",
        "Content-Type": "application/json",
    },
    json={"instances": [[6.8, 2.8, 4.8, 1.4]]},
)
print(response.json())`
    : ''

  return (
    <div style={{ padding: 0 }}>
      {tokenVisible && authToken && (
        <Modal
          open={tokenVisible}
          title="API Token"
          onCancel={() => {
            setTokenVisible(false)
            navigate(location.pathname, { replace: true, state: {} })
          }}
          footer={[
            <Button
              key="close"
              type="primary"
              onClick={() => {
                setTokenVisible(false)
                navigate(location.pathname, { replace: true, state: {} })
              }}
            >
              我已保存
            </Button>,
          ]}
          width={560}
        >
          <Alert type="warning" message="请妥善保存，仅显示一次" style={{ marginBottom: 12 }} />
          <Typography.Paragraph copyable code style={{ wordBreak: 'break-all' }}>
            {authToken}
          </Typography.Paragraph>
        </Modal>
      )}

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

      <CanaryStartModal
        open={canaryStartModalOpen}
        onCancel={() => setCanaryStartModalOpen(false)}
        onSubmit={(data) => startCanaryMutation.mutate(data)}
        loading={startCanaryMutation.isPending}
        currentModelVersionId={svc.modelVersionId}
        registeredModelId={svc.modelVersion?.registeredModelId}
        gpuCount={svc.gpuCount}
        replicas={svc.replicas}
      />

      <CanaryTrafficModal
        open={canaryTrafficModalOpen}
        onCancel={() => setCanaryTrafficModalOpen(false)}
        onSubmit={(data) => updateTrafficMutation.mutate(data)}
        loading={updateTrafficMutation.isPending}
        currentPercent={svc.canaryTrafficPercent ?? 0}
      />

      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          推理服务详情 - {svc.name}
        </Typography.Title>
        <Button onClick={() => navigate('/inference')}>返回列表</Button>
      </div>

      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <span style={{ fontSize: 14 }}>状态:</span>
            {svc.errorMessage && svc.status === 'failed' ? (
              <Tooltip title={svc.errorMessage}>
                <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
              </Tooltip>
            ) : (
              <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
            )}
            {svc.gpuCount > 0 && <span>GPU: {svc.gpuCount} 张</span>}
            <span>
              副本:{' '}
              {isAutoMode ? (
                <Tooltip title={`当前: ${svc.replicas}`}>
                  {svc.minReplicas}-{svc.maxReplicas}
                </Tooltip>
              ) : (
                svc.replicas
              )}
            </span>
            {canWrite && (
              <>
                <Divider type="vertical" />
                <Space size={4}>
                  <span style={{ fontSize: 12, color: '#888' }}>自动伸缩</span>
                  <Switch
                    size="small"
                    checked={isAutoMode}
                    onChange={handleToggleAutoScaling}
                    disabled={svc.status === 'failed'}
                  />
                </Space>
              </>
            )}
            {isAutoMode && (
              <Tag icon={<ThunderboltOutlined />} color="blue">
                自动伸缩
              </Tag>
            )}
            {isAutoMode && canWrite && (
              <Button size="small" type="link" onClick={() => setAutoScalingModalOpen(true)}>
                伸缩配置
              </Button>
            )}
            {showScaleBtn && !isAutoMode && (
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
                <Button size="small">调整副本</Button>
              </Popover>
            )}
          </Space>
        }
      >
        {isAutoMode && svc.minReplicas === 0 && svc.status === 'stopped' && (
          <Alert
            type="info"
            message="自动缩容到零，流量恢复后将自动扩容"
            showIcon
            style={{ marginTop: 8 }}
          />
        )}
        {isAutoMode && svc.minReplicas === 0 && svc.status !== 'stopped' && (
          <Alert
            type="info"
            message="支持缩容到零，无流量时自动释放 GPU 资源"
            showIcon
            style={{ marginTop: 8 }}
          />
        )}
        {isAutoMode && (
          <div style={{ marginTop: 8, fontSize: 12, color: '#666' }}>
            当前副本: {svc.replicas} | 指标:{' '}
            {svc.targetMetricType === 'cpu' ? 'CPU 利用率' : '并发请求数'}{' '}
            {svc.targetMetricValue &&
              `> ${svc.targetMetricValue}${svc.targetMetricType === 'cpu' ? '%' : ''}`}
          </div>
        )}
        {svc.status === 'failed' && svc.errorMessage && (
          <Alert
            type="error"
            message="推理服务异常"
            description={svc.errorMessage}
            showIcon
            style={{ marginTop: 8 }}
          />
        )}
      </Card>

      {/* Canary Section */}
      <CanarySection
        svc={svc}
        canaryStatusData={canaryStatusData}
        canaryEvents={canaryStatusData?.canaryEvents ?? []}
        onStartCanary={() => setCanaryStartModalOpen(true)}
        onAdjustTraffic={() => setCanaryTrafficModalOpen(true)}
        onPromote={() => promoteCanaryMutation.mutate(id!)}
        onRollback={() => rollbackCanaryMutation.mutate(id!)}
        onRetry={() => rollbackCanaryMutation.mutate(id!)}
        canWrite={canWrite}
        canManage={canManage}
        promoteLoading={promoteCanaryMutation.isPending}
        rollbackLoading={rollbackCanaryMutation.isPending}
      />

      <Card size="small" style={{ marginBottom: 16 }} title="端点与认证">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="推理 URL">
            {proxyUrl ? (
              <Space>
                <Typography.Text copyable={{ text: proxyUrl }} style={{ maxWidth: 500 }} ellipsis>
                  {proxyUrl}
                </Typography.Text>
              </Space>
            ) : (
              <Tag>部署后生成</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="API Token">
            <Space>
              {svc.hasToken ? (
                <>
                  <Tag color="success">已生成</Tag>
                  {canWrite && (
                    <Popconfirm
                      title="重新生成 Token"
                      description="重新生成后旧 Token 将立即失效，确定继续？"
                      onConfirm={() => regenerateMutation.mutate()}
                      okText="确认"
                      cancelText="取消"
                    >
                      <Button
                        size="small"
                        icon={<SyncOutlined />}
                        loading={regenerateMutation.isPending}
                      >
                        重新生成
                      </Button>
                    </Popconfirm>
                  )}
                </>
              ) : (
                <Tag>未生成</Tag>
              )}
            </Space>
          </Descriptions.Item>
        </Descriptions>
        {proxyUrl && (
          <Collapse
            size="small"
            style={{ marginTop: 12 }}
            items={[
              {
                key: 'examples',
                label: '调用示例',
                children: (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div>
                      <Typography.Text strong>curl</Typography.Text>
                      <Typography.Paragraph
                        copyable
                        code
                        style={{ whiteSpace: 'pre-wrap', marginBottom: 0, marginTop: 4 }}
                      >
                        {curlExample}
                      </Typography.Paragraph>
                    </div>
                    <div>
                      <Typography.Text strong>Python</Typography.Text>
                      <Typography.Paragraph
                        copyable
                        code
                        style={{ whiteSpace: 'pre-wrap', marginBottom: 0, marginTop: 4 }}
                      >
                        {pythonExample}
                      </Typography.Paragraph>
                    </div>
                  </div>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Card size="small" title="基本信息">
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="CPU">{svc.cpu} 核</Descriptions.Item>
          <Descriptions.Item label="内存">{svc.memory}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>
            {svc.description || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{svc.createdAt}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{svc.updatedAt}</Descriptions.Item>
        </Descriptions>
      </Card>

      {svc.kserveName && svc.status !== 'pending' && svc.status !== 'stopped' && (
        <Card size="small" style={{ marginTop: 16 }} title="事件日志">
          {eventsLoading ? (
            <Spin />
          ) : events.length === 0 ? (
            <Typography.Text type="secondary">暂无事件记录</Typography.Text>
          ) : (
            <Table<InferenceServiceEvent>
              dataSource={events}
              rowKey={(record) => `${record.type}-${record.reason}-${record.lastTimestamp}`}
              size="small"
              pagination={false}
              scroll={{ x: 800 }}
              columns={[
                {
                  title: '类型',
                  dataIndex: 'type',
                  width: 80,
                  render: (type: string) => (
                    <Tag color={type === 'Warning' ? 'red' : 'blue'}>
                      {type === 'Warning' ? '警告' : '正常'}
                    </Tag>
                  ),
                },
                {
                  title: '原因',
                  dataIndex: 'reason',
                  width: 120,
                },
                {
                  title: '消息',
                  dataIndex: 'message',
                  ellipsis: { showTitle: false },
                  render: (msg: string) => (
                    <Tooltip title={msg}>
                      <span>{msg}</span>
                    </Tooltip>
                  ),
                },
                {
                  title: '资源',
                  width: 160,
                  render: (_: unknown, record: InferenceServiceEvent) =>
                    `${record.involvedObjectKind}/${record.involvedObjectName}`,
                },
                {
                  title: '时间',
                  dataIndex: 'lastTimestamp',
                  width: 180,
                  render: (ts: string | null) =>
                    ts ? dayjs(ts).format('YYYY-MM-DD HH:mm:ss') : '—',
                },
                {
                  title: '次数',
                  dataIndex: 'count',
                  width: 60,
                },
              ]}
            />
          )}
        </Card>
      )}
    </div>
  )
}

/* ── Canary Section Component ──────────────────────────────────────────── */

function CanarySection({
  svc,
  canaryStatusData,
  canaryEvents,
  onStartCanary,
  onAdjustTraffic,
  onPromote,
  onRollback,
  onRetry,
  canWrite,
  canManage,
  promoteLoading,
  rollbackLoading,
}: {
  svc: import('@/types/inference').InferenceService
  canaryStatusData: import('@/types/inference').CanaryStatusResponse | undefined
  canaryEvents: InferenceServiceEvent[]
  onStartCanary: () => void
  onAdjustTraffic: () => void
  onPromote: () => void
  onRollback: () => void
  onRetry: () => void
  canWrite: boolean
  canManage: boolean
  promoteLoading: boolean
  rollbackLoading: boolean
}) {
  const canaryCfg = CANARY_STATUS_CONFIG[svc.canaryStatus] ?? {
    color: 'default',
    text: svc.canaryStatus,
  }

  const hasActiveCanary = svc.canaryStatus !== 'none'

  // No canary - show start button
  if (!hasActiveCanary) {
    if (svc.status !== 'running' || !canWrite) return null
    return (
      <Card size="small" style={{ marginBottom: 16 }} title="金丝雀发布">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography.Text type="secondary">
            当前服务运行稳定，可启动金丝雀发布逐步上线新模型版本
          </Typography.Text>
          <Button type="primary" icon={<ExperimentOutlined />} onClick={onStartCanary}>
            启动金丝雀发布
          </Button>
        </div>
      </Card>
    )
  }

  const canaryPercent = svc.canaryTrafficPercent ?? 0
  const stablePercent = 100 - canaryPercent

  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={
        <Space>
          <span>金丝雀发布</span>
          <Tag color={canaryCfg.color}>{canaryCfg.text}</Tag>
          {svc.canaryStatus === 'running' && <Tag color="blue">{canaryPercent}% 流量</Tag>}
        </Space>
      }
    >
      {/* Deploying status */}
      {svc.canaryStatus === 'deploying' && (
        <Alert
          type="info"
          message="金丝雀版本正在部署中，请等待就绪..."
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      {/* Failed status */}
      {svc.canaryStatus === 'failed' && (
        <Alert
          type="error"
          message="金丝雀版本部署失败"
          description="请检查事件日志了解失败原因"
          showIcon
          action={
            canWrite ? (
              <Button size="small" danger loading={rollbackLoading} onClick={onRetry}>
                清理并重试
              </Button>
            ) : undefined
          }
          style={{ marginBottom: 12 }}
        />
      )}

      {/* Running status - traffic visualization */}
      {svc.canaryStatus === 'running' && (
        <>
          <Alert
            type="info"
            message={`金丝雀版本正在接收 ${canaryPercent}% 的流量`}
            description="确认指标正常后再逐步提升流量"
            showIcon
            style={{ marginBottom: 16 }}
          />

          <div style={{ marginBottom: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ fontSize: 12 }}>
                稳定版本 (
                {svc.modelVersion?.versionNumber ? `v${svc.modelVersion.versionNumber}` : '当前'})
              </span>
              <span style={{ fontSize: 12, fontWeight: 500 }}>
                金丝雀 (
                {canaryStatusData?.canaryModelVersion
                  ? `v${canaryStatusData.canaryModelVersion.versionNumber}`
                  : '新版本'}
                )
              </span>
            </div>
            <Progress
              percent={100}
              success={{ percent: stablePercent, strokeColor: '#1677ff' }}
              strokeColor="#52c41a"
              showInfo={false}
              size="small"
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
              <span style={{ fontSize: 12, color: '#1677ff' }}>{stablePercent}% 流量</span>
              <span style={{ fontSize: 12, color: '#52c41a' }}>{canaryPercent}% 流量</span>
            </div>
          </div>

          {canWrite && (
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <Button onClick={onAdjustTraffic}>调整流量</Button>
              {canManage && (
                <Popconfirm
                  title="提升金丝雀版本"
                  description="确认将金丝雀版本提升为稳定版本？此操作不可撤销"
                  onConfirm={onPromote}
                  okText="确认提升"
                  cancelText="取消"
                >
                  <Button type="primary" loading={promoteLoading}>
                    提升为稳定版本
                  </Button>
                </Popconfirm>
              )}
              <Popconfirm
                title="回滚金丝雀"
                description="确认回滚金丝雀？金丝雀版本将被删除"
                onConfirm={onRollback}
                okText="确认回滚"
                cancelText="取消"
              >
                <Button danger loading={rollbackLoading}>
                  回滚
                </Button>
              </Popconfirm>
            </div>
          )}
        </>
      )}

      {/* Canary events */}
      {svc.canaryKserveName && svc.canaryStatus !== 'none' && canaryEvents.length > 0 && (
        <Collapse
          size="small"
          items={[
            {
              key: 'canary-events',
              label: `金丝雀事件 (${canaryEvents.length})`,
              children: (
                <Table<InferenceServiceEvent>
                  dataSource={canaryEvents}
                  rowKey={(record) =>
                    `canary-${record.type}-${record.reason}-${record.lastTimestamp}`
                  }
                  size="small"
                  pagination={{ pageSize: 5, size: 'small' }}
                  scroll={{ x: 700 }}
                  columns={[
                    {
                      title: '类型',
                      dataIndex: 'type',
                      width: 70,
                      render: (type: string) => (
                        <Tag color={type === 'Warning' ? 'red' : 'blue'} style={{ fontSize: 11 }}>
                          {type === 'Warning' ? '警告' : '正常'}
                        </Tag>
                      ),
                    },
                    { title: '原因', dataIndex: 'reason', width: 110 },
                    {
                      title: '消息',
                      dataIndex: 'message',
                      ellipsis: { showTitle: false },
                      render: (msg: string) => (
                        <Tooltip title={msg}>
                          <span>{msg}</span>
                        </Tooltip>
                      ),
                    },
                    {
                      title: '时间',
                      dataIndex: 'lastTimestamp',
                      width: 160,
                      render: (ts: string | null) =>
                        ts ? dayjs(ts).format('MM-DD HH:mm:ss') : '—',
                    },
                  ]}
                />
              ),
            },
          ]}
        />
      )}
    </Card>
  )
}

/* ── Canary Start Modal ──────────────────────────────────────────────────── */

function CanaryStartModal({
  open,
  onCancel,
  onSubmit,
  loading,
  currentModelVersionId,
  registeredModelId,
  gpuCount,
  replicas,
}: {
  open: boolean
  onCancel: () => void
  onSubmit: (data: { canaryModelVersionId: string; canaryTrafficPercent: number }) => void
  loading: boolean
  currentModelVersionId: string
  registeredModelId?: string
  gpuCount: number
  replicas: number
}) {
  const [form] = Form.useForm()
  const { quota } = useResourceQuota()
  const trafficPercent = Form.useWatch('canaryTrafficPercent', form) ?? 10

  const { data: modelDetail } = useQuery({
    queryKey: ['model', registeredModelId],
    queryFn: () => getModel(registeredModelId!),
    enabled: !!registeredModelId && open,
  })

  const availableVersions =
    modelDetail?.versions.filter(
      (v) => v.id !== currentModelVersionId && v.status === 'available',
    ) ?? []

  const gpuPreview = gpuCount * replicas
  const gpuAvailable = quota ? quota.gpu.total - quota.gpu.used : 0

  const handleFinish = () => {
    form.validateFields().then((values) => {
      onSubmit({
        canaryModelVersionId: values.canaryModelVersionId,
        canaryTrafficPercent: values.canaryTrafficPercent,
      })
    })
  }

  return (
    <Modal
      open={open}
      title="启动金丝雀发布"
      onCancel={onCancel}
      onOk={handleFinish}
      confirmLoading={loading}
      okText="启动金丝雀"
      cancelText="取消"
      width={520}
      destroyOnClose
    >
      <Form form={form} layout="vertical" initialValues={{ canaryTrafficPercent: 10 }}>
        <Form.Item
          name="canaryModelVersionId"
          label="金丝雀模型版本"
          rules={[{ required: true, message: '请选择金丝雀模型版本' }]}
        >
          <Select
            placeholder="选择模型版本"
            options={availableVersions.map((v) => ({
              label: `v${v.versionNumber} — ${v.description || v.storagePath}`,
              value: v.id,
            }))}
            notFoundContent="没有可用的模型版本"
          />
        </Form.Item>
        <Form.Item label="初始流量比例" style={{ marginBottom: 8 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <Slider
              min={1}
              max={99}
              value={trafficPercent}
              onChange={(v) => form.setFieldValue('canaryTrafficPercent', v)}
              style={{ flex: 1 }}
            />
            <InputNumber
              min={1}
              max={99}
              value={trafficPercent}
              onChange={(v) => form.setFieldValue('canaryTrafficPercent', v ?? 10)}
              style={{ width: 70 }}
              addonAfter="%"
            />
          </div>
        </Form.Item>
        <Form.Item name="canaryTrafficPercent" hidden>
          <InputNumber />
        </Form.Item>

        {gpuCount > 0 && (
          <div
            style={{ padding: '8px 12px', background: '#fafafa', borderRadius: 6, marginTop: 8 }}
          >
            <Typography.Text style={{ fontSize: 12 }}>
              资源预估: {gpuCount} GPU × {replicas} 副本 = {gpuPreview} GPU
              {quota && (
                <span
                  style={{
                    marginLeft: 8,
                    color: gpuPreview > gpuAvailable ? '#ff4d4f' : '#52c41a',
                  }}
                >
                  (可用: {gpuAvailable} GPU)
                </span>
              )}
            </Typography.Text>
          </div>
        )}
      </Form>
    </Modal>
  )
}

/* ── Canary Traffic Modal ──────────────────────────────────────────────────── */

function CanaryTrafficModal({
  open,
  onCancel,
  onSubmit,
  loading,
  currentPercent,
}: {
  open: boolean
  onCancel: () => void
  onSubmit: (data: { canaryTrafficPercent: number }) => void
  loading: boolean
  currentPercent: number
}) {
  const [percent, setPercent] = useState(currentPercent)

  const handleFinish = () => {
    onSubmit({ canaryTrafficPercent: percent })
  }

  return (
    <Modal
      open={open}
      title="调整金丝雀流量"
      onCancel={onCancel}
      onOk={handleFinish}
      confirmLoading={loading}
      okText="确认调整"
      cancelText="取消"
      destroyOnClose
    >
      <div style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
          <Slider
            min={0}
            max={100}
            value={percent}
            onChange={setPercent}
            style={{ flex: 1 }}
            marks={{
              0: { label: '回滚' },
              25: '25%',
              50: '50%',
              75: '75%',
              100: { label: '完全提升' },
            }}
          />
          <InputNumber
            min={0}
            max={100}
            value={percent}
            onChange={(v) => setPercent(v ?? 0)}
            style={{ width: 80 }}
            addonAfter="%"
          />
        </div>
        {percent === 0 && (
          <Alert type="warning" message="设置为 0% 将回滚金丝雀，金丝雀版本将被删除" showIcon />
        )}
        {percent === 100 && (
          <Alert
            type="info"
            message="设置为 100% 将提升金丝雀为稳定版本，此操作不可撤销"
            showIcon
          />
        )}
        {percent > 0 && percent < 100 && (
          <Alert type="info" message="确认指标正常后再逐步提升流量" showIcon />
        )}
      </div>
    </Modal>
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
      destroyOnClose
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
