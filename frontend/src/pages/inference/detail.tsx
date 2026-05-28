import { useState } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Form,
  InputNumber,
  Modal,
  Popconfirm,
  Progress,
  Select,
  Slider,
  Space,
  Spin,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { ExperimentOutlined, ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { useResourceQuota } from '@/hooks/useResourceQuota'
import {
  getInferenceService,
  getInferenceServiceEvents,
  regenerateToken,
  startCanary,
  startInferenceService,
  stopInferenceService,
  updateCanaryTraffic,
  promoteCanary,
  rollbackCanary,
  getCanaryStatus,
} from '@/services/inference'
import { getModel } from '@/services/models'
import { MonitorTab } from './components/MonitorTab'
import { ConfigTab } from './components/ConfigTab'
import type { InferenceServiceEvent } from '@/types/inference'

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

const GIGITAL_STORAGE_KEY = 'inference_guide_dismissed'

export default function InferenceServiceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tokenVisible, setTokenVisible] = useState(() => !!location.state?.authToken)
  const [canaryStartModalOpen, setCanaryStartModalOpen] = useState(false)
  const [canaryTrafficModalOpen, setCanaryTrafficModalOpen] = useState(false)
  const [showGuide, setShowGuide] = useState(() => {
    if (typeof window !== 'undefined') {
      return !localStorage.getItem(GIGITAL_STORAGE_KEY)
    }
    return true
  })
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
    enabled:
      !!id &&
      svc?.serviceType !== 'custom' &&
      !!svc?.canaryKserveName &&
      svc.canaryStatus !== 'none',
    refetchInterval: svc?.canaryStatus === 'deploying' ? 5000 : 30000,
  })

  const startMutation = useMutation({
    mutationFn: () => startInferenceService(id!),
    onSuccess: () => {
      getMessageInstance()?.success('推理服务启动中')
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => stopInferenceService(id!),
    onSuccess: () => {
      getMessageInstance()?.success('推理服务已停止')
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
    },
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
    enabled: !!id && svc?.status !== 'pending' && svc?.status !== 'stopped',
    refetchInterval: svc?.status === 'running' || svc?.status === 'deploying' ? 30000 : false,
  })

  if (isLoading) return <Spin />
  if (!svc) return null

  const statusCfg = STATUS_CONFIG[svc.status] ?? { color: 'default', text: svc.status }
  const isAutoMode = svc.scalingMode === 'auto'

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

  const handleDismissGuide = () => {
    setShowGuide(false)
    if (typeof window !== 'undefined') {
      localStorage.setItem(GIGITAL_STORAGE_KEY, 'true')
    }
  }

  const copyEndpointUrl = () => {
    if (proxyUrl) {
      navigator.clipboard.writeText(proxyUrl)
      getMessageInstance()?.success('端点 URL 已复制')
    }
  }

  const tabItems = [
    {
      key: 'overview',
      label: '概览',
      children: (
        <OverviewTab
          svc={svc}
          statusCfg={statusCfg}
          canWrite={canWrite}
          proxyUrl={proxyUrl}
          curlExample={curlExample}
          pythonExample={pythonExample}
          regenerateMutation={regenerateMutation}
          canaryStatusData={canaryStatusData}
          canaryEvents={canaryStatusData?.canaryEvents ?? []}
          onStartCanary={() => setCanaryStartModalOpen(true)}
          onAdjustTraffic={() => setCanaryTrafficModalOpen(true)}
          onPromote={() => promoteCanaryMutation.mutate(id!)}
          onRollback={() => rollbackCanaryMutation.mutate(id!)}
          canManage={canManage}
          promoteLoading={promoteCanaryMutation.isPending}
          rollbackLoading={rollbackCanaryMutation.isPending}
        />
      ),
    },
    {
      key: 'monitor',
      label: '监控',
      children: (
        <MonitorTab serviceStatus={svc.status} events={events} eventsLoading={eventsLoading} />
      ),
    },
    {
      key: 'config',
      label: '配置',
      children: <ConfigTab service={svc} canWrite={canWrite} />,
    },
  ]

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

      {/* 部署成功引导卡片 */}
      {showGuide && svc.status === 'running' && proxyUrl && (
        <Card
          style={{
            marginBottom: 16,
            background: '#f6ffed',
            border: '1px solid #b7eb8f',
          }}
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Title level={5} style={{ margin: 0 }}>
              推理服务部署成功！
            </Typography.Title>
            <Typography.Text>端点已就绪，可以开始使用了</Typography.Text>
            <Space>
              <Button onClick={copyEndpointUrl}>复制端点</Button>
              <Button
                onClick={() =>
                  document.querySelector<HTMLElement>('[data-tab-key="monitor"]')?.click()
                }
              >
                查看监控
              </Button>
              <Button
                onClick={() =>
                  document.querySelector<HTMLElement>('[data-tab-key="config"]')?.click()
                }
              >
                配置伸缩
              </Button>
            </Space>
            <Button type="link" size="small" onClick={handleDismissGuide}>
              不再显示
            </Button>
          </Space>
        </Card>
      )}

      {/* 顶部状态卡片（始终可见） */}
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
            {isAutoMode && <Tag color="blue">自动伸缩</Tag>}
          </Space>
        }
        extra={
          <Space>
            {canWrite && svc.status === 'stopped' && (
              <Popconfirm
                title="确认启动该服务？"
                description="将恢复之前的副本配置并重新部署"
                onConfirm={() => startMutation.mutate()}
                okText="确认"
                cancelText="取消"
              >
                <Button size="small" type="primary" loading={startMutation.isPending}>
                  启动
                </Button>
              </Popconfirm>
            )}
            {canWrite && ['running', 'deploying', 'pending'].includes(svc.status) && (
              <Popconfirm
                title="确认停止该服务？"
                description="停止后副本数将设为 0，配置保留"
                onConfirm={() => stopMutation.mutate()}
                okText="确认"
                cancelText="取消"
              >
                <Button size="small" danger loading={stopMutation.isPending}>
                  停止
                </Button>
              </Popconfirm>
            )}
            <Button
              size="small"
              icon={<ReloadOutlined />}
              onClick={() => {
                queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
                queryClient.invalidateQueries({ queryKey: ['canaryStatus', id] })
              }}
            >
              刷新
            </Button>
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

      {/* Tab 组织内容 */}
      <Tabs defaultActiveKey="overview" items={tabItems} />
    </div>
  )
}

/* ── OverviewTab Component ──────────────────────────────────────────────── */

function OverviewTab({
  svc,
  statusCfg,
  canWrite,
  proxyUrl,
  curlExample,
  pythonExample,
  regenerateMutation,
  canaryStatusData,
  canaryEvents,
  onStartCanary,
  onAdjustTraffic,
  onPromote,
  onRollback,
  canManage,
  promoteLoading,
  rollbackLoading,
}: {
  svc: import('@/types/inference').InferenceService
  statusCfg: { color: string; text: string }
  canWrite: boolean
  proxyUrl: string
  curlExample: string
  pythonExample: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  regenerateMutation: { mutate: (...args: any[]) => void; isPending: boolean }
  canaryStatusData: import('@/types/inference').CanaryStatusResponse | undefined
  canaryEvents: InferenceServiceEvent[]
  onStartCanary: () => void
  onAdjustTraffic: () => void
  onPromote: () => void
  onRollback: () => void
  canManage: boolean
  promoteLoading: boolean
  rollbackLoading: boolean
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 基本信息卡片 */}
      <Card size="small" title="基本信息">
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="服务类型">
            <Tag color={svc.serviceType === 'custom' ? 'purple' : 'blue'}>
              {svc.serviceType === 'custom' ? '自定义容器' : '模型推理'}
            </Tag>
          </Descriptions.Item>
          {svc.serviceType === 'model' ? (
            <Descriptions.Item label="模型版本">
              {svc.modelVersion
                ? `v${svc.modelVersion.versionNumber}`
                : (svc.modelVersionId?.slice(0, 8) ?? '—')}
            </Descriptions.Item>
          ) : (
            <>
              <Descriptions.Item label="容器端口">{svc.containerPort ?? '—'}</Descriptions.Item>
              <Descriptions.Item label="启动命令">
                {svc.command || <Tag>默认</Tag>}
              </Descriptions.Item>
              <Descriptions.Item label="启动参数">{svc.args || <Tag>默认</Tag>}</Descriptions.Item>
            </>
          )}
          <Descriptions.Item label="状态">
            <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="GPU">
            {svc.gpuCount > 0 ? `${svc.gpuCount} 张` : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="内存">{svc.memory}</Descriptions.Item>
          <Descriptions.Item label="描述">{svc.description || '—'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{svc.createdAt}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{svc.updatedAt}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 端点与认证卡片 */}
      <Card size="small" title="端点与认证">
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

      {/* 金丝雀发布卡片 - 仅模型推理服务 */}
      {svc.serviceType !== 'custom' && (
        <CanarySection
          svc={svc}
          canaryStatusData={canaryStatusData}
          canaryEvents={canaryEvents}
          onStartCanary={onStartCanary}
          onAdjustTraffic={onAdjustTraffic}
          onPromote={onPromote}
          onRollback={onRollback}
          canWrite={canWrite}
          canManage={canManage}
          promoteLoading={promoteLoading}
          rollbackLoading={rollbackLoading}
        />
      )}
    </div>
  )
}

/* ── CanarySection Component ──────────────────────────────────────────── */

function CanarySection({
  svc,
  canaryStatusData,
  canaryEvents,
  onStartCanary,
  onAdjustTraffic,
  onPromote,
  onRollback,
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

  if (!hasActiveCanary) {
    if (svc.status !== 'running' || !canWrite) return null
    return (
      <Card size="small" title="金丝雀发布">
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
      title={
        <Space>
          <span>金丝雀发布</span>
          <Tag color={canaryCfg.color}>{canaryCfg.text}</Tag>
          {svc.canaryStatus === 'running' && <Tag color="blue">{canaryPercent}% 流量</Tag>}
        </Space>
      }
    >
      {svc.canaryStatus === 'deploying' && (
        <Alert
          type="info"
          message="金丝雀版本正在部署中，请等待就绪..."
          showIcon
          style={{ marginBottom: 12 }}
        />
      )}

      {svc.canaryStatus === 'failed' && (
        <Alert
          type="error"
          message="金丝雀版本部署失败"
          description="请检查监控 Tab 中的事件日志了解失败原因"
          showIcon
          action={
            canWrite ? (
              <Button size="small" danger loading={rollbackLoading} onClick={onRollback}>
                清理并重试
              </Button>
            ) : undefined
          }
          style={{ marginBottom: 12 }}
        />
      )}

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
  currentModelVersionId?: string
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
      destroyOnHidden
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
      destroyOnHidden
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
