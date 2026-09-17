import { useState } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { ReloadOutlined, SyncOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { copyToClipboard } from '@/utils/clipboard'
import { formatDate } from '@/utils/format'
import { useRbacStore } from '@/stores/rbacStore'
import {
  getInferenceService,
  getInferenceServiceEvents,
  getInferenceServiceMetrics,
  regenerateToken,
  startInferenceService,
  stopInferenceService,
} from '@/services/inference'
import { MonitorTab } from './components/MonitorTab'
import { ConfigTab } from './components/ConfigTab'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'warning', text: '等待中' },
  deploying: { color: 'processing', text: '部署中' },
  running: { color: 'success', text: '运行中' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

const GIGITAL_STORAGE_KEY = 'inference_guide_dismissed'

export default function InferenceServiceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tokenVisible, setTokenVisible] = useState(() => !!location.state?.authToken)
  const [showGuide, setShowGuide] = useState(() => {
    if (typeof window !== 'undefined') {
      return !localStorage.getItem(GIGITAL_STORAGE_KEY)
    }
    return true
  })
  const authToken = (location.state as { authToken?: string } | null)?.authToken

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('inference_services:write')

  const { data: svc, isLoading } = useQuery({
    queryKey: ['inferenceService', id],
    queryFn: () => getInferenceService(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      if (status && ['pending', 'deploying'].includes(status)) return 5000
      return false
    },
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

  const { data: events = [], isLoading: eventsLoading } = useQuery({
    queryKey: ['inferenceServiceEvents', id],
    queryFn: () => getInferenceServiceEvents(id!),
    enabled: !!id && svc?.status !== 'pending' && svc?.status !== 'stopped',
    refetchInterval: svc?.status === 'running' || svc?.status === 'deploying' ? 30000 : false,
  })

  // GPU metrics query with polling
  const isRunning = svc?.status === 'running'
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: ['inferenceServiceMetrics', id],
    queryFn: () => getInferenceServiceMetrics(id!),
    enabled: !!id && svc?.status === 'running' && svc?.gpuCount > 0,
    refetchInterval: isRunning ? 10_000 : false,
  })

  const prometheusAvailable = metricsData?.prometheusAvailable ?? false

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

  const copyEndpointUrl = async () => {
    if (proxyUrl) {
      const ok = await copyToClipboard(proxyUrl)
      if (ok) getMessageInstance()?.success('端点 URL 已复制')
      else getMessageInstance()?.error('复制失败，请手动复制')
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
        />
      ),
    },
    {
      key: 'monitor',
      label: '监控',
      children: (
        <MonitorTab
          serviceStatus={svc.status}
          events={events}
          eventsLoading={eventsLoading}
          gpuMetrics={metricsData?.gpuMetrics ?? []}
          gpuUtilizationHistory={metricsData?.gpuUtilizationHistory ?? []}
          metricsLoading={metricsLoading}
          prometheusAvailable={prometheusAvailable}
        />
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
}: {
  svc: import('@/types/inference').InferenceService
  statusCfg: { color: string; text: string }
  canWrite: boolean
  proxyUrl: string
  curlExample: string
  pythonExample: string
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  regenerateMutation: { mutate: (...args: any[]) => void; isPending: boolean }
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 基本信息卡片 */}
      <Card size="small" title="基本信息">
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="容器端口">{svc.containerPort ?? '—'}</Descriptions.Item>
          <Descriptions.Item label="启动命令">{svc.command || <Tag>默认</Tag>}</Descriptions.Item>
          <Descriptions.Item label="启动参数">{svc.args || <Tag>默认</Tag>}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
          </Descriptions.Item>
          {svc.modelVersion && (
            <Descriptions.Item label="模型" span={2}>
              <Space>
                <span>{svc.modelVersion.modelName}</span>
                <Tag color="blue">v{svc.modelVersion.versionNumber}</Tag>
              </Space>
            </Descriptions.Item>
          )}
          <Descriptions.Item label="GPU">
            {svc.gpuCount > 0 ? `${svc.gpuCount} 张` : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="内存">{svc.memory}</Descriptions.Item>
          <Descriptions.Item label="描述">{svc.description || '—'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDate(svc.createdAt)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{formatDate(svc.updatedAt)}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 端点与认证卡片 */}
      <Card size="small" title="端点与认证">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="推理 URL">
            {proxyUrl ? (
              <Space>
                <Typography.Text copyable={{ text: proxyUrl }} style={{ maxWidth: 420 }} ellipsis>
                  {proxyUrl}
                </Typography.Text>
                <Typography.Link href={proxyUrl} target="_blank" rel="noopener noreferrer">
                  在浏览器打开
                </Typography.Link>
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
    </div>
  )
}
