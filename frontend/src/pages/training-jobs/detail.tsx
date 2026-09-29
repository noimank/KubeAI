import { useMemo, useState } from 'react'
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Steps,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { formatDate } from '@/utils/format'
import {
  CheckCircleOutlined,
  DesktopOutlined,
  ExperimentOutlined,
  InboxOutlined,
  RocketOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import LogStream from '@/components/LogStream'
import GpuMetricsChart from '@/components/GpuMetricsChart'
import { useGpuAlerts } from '@/hooks/useGpuAlerts'
import { useRbacStore } from '@/stores/rbacStore'
import { useAuthStore } from '@/stores/authStore'
import { useTenantStore } from '@/stores/tenantStore'
import FileBrowser from '@/components/FileBrowser'
import {
  buildLogStreamWsUrl,
  getTrainingJob,
  getTrainingJobLogs,
  getTrainingJobMetrics,
  getTrainingJobPods,
  stopTrainingJob,
  retryTrainingJob,
  deleteTrainingJob,
} from '@/services/training-jobs'
import { registerModel } from '@/services/models'
import ExperimentPanel from './components/ExperimentPanel'
import { getMessageInstance } from '@/utils/messageHolder'
import { TRAINING_JOB_STATUS_CONFIG } from '@/utils/constants'
import type { TrainingJobStatus } from '@/types/training-job'

const STATUS_STEPS = [
  { key: 'pending', title: '等待' },
  { key: 'queued', title: '排队' },
  { key: 'running', title: '运行' },
  { key: 'succeeded', title: '完成' },
]

const STREAMABLE_STATUSES: TrainingJobStatus[] = ['pending', 'queued', 'initializing', 'running']
const HISTORY_STATUSES: TrainingJobStatus[] = ['succeeded', 'failed', 'stopped']
const NOT_STARTED_STATUSES: TrainingJobStatus[] = ['pending', 'queued']

function getStepIndex(status: TrainingJobStatus): number {
  const map: Record<string, number> = {
    pending: 0,
    queued: 1,
    initializing: 1,
    running: 2,
    succeeded: 3,
    failed: 2,
    stopped: 2,
  }
  return map[status] ?? 0
}

function getStepStatus(jobStatus: TrainingJobStatus): 'process' | 'finish' | 'error' | 'wait' {
  if (jobStatus === 'failed') return 'error'
  if (jobStatus === 'stopped') return 'error'
  if (['succeeded'].includes(jobStatus)) return 'finish'
  return 'process'
}

function formatDuration(start?: string, end?: string): string {
  if (!start) return '—'
  const startDate = new Date(start)
  const endDate = end ? new Date(end) : new Date()
  const diffMs = endDate.getTime() - startDate.getTime()
  if (diffMs < 0) return '—'
  const hours = Math.floor(diffMs / 3600000)
  const minutes = Math.floor((diffMs % 3600000) / 60000)
  const seconds = Math.floor((diffMs % 60000) / 1000)
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

export default function TrainingJobDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  // 初始 Tab 支持 ?tab= 深链 (训练任务列表「实验详情」按钮跳转实验 Tab)
  const [activeTab, setActiveTab] = useState(searchParams.get('tab') ?? 'overview')
  const handleTabChange = (key: string) => {
    setActiveTab(key)
    const next = new URLSearchParams(searchParams)
    if (key === 'overview') next.delete('tab')
    else next.set('tab', key)
    setSearchParams(next, { replace: true })
  }
  const [selectedPod, setSelectedPod] = useState<string | undefined>(undefined)
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [modelName, setModelName] = useState('')
  const [modelDesc, setModelDesc] = useState('')
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const queryClient = useQueryClient()

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('training_jobs:write')
  const canWriteModels = hasPermission('models:write')

  // 文件浏览器的虚拟根 — 裸前缀由后端 filesystem_browser 自动绑定到当前用户 / 租户.
  const authUser = useAuthStore((s) => s.user)
  const currentTenant = useTenantStore((s) => s.currentTenant)
  const browserRoots = useMemo<string[]>(
    () => (authUser && currentTenant ? ['/kubeai/home', '/kubeai/workspace'] : []),
    [authUser, currentTenant],
  )

  const {
    data: job,
    isLoading,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['trainingJob', id],
    queryFn: () => getTrainingJob(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return ['pending', 'queued', 'initializing', 'running'].includes(status ?? '') ? 5000 : false
    },
  })

  const stopMutation = useMutation({
    mutationFn: stopTrainingJob,
    onSuccess: () => {
      getMessageInstance()?.success('任务已停止')
      queryClient.invalidateQueries({ queryKey: ['trainingJob', id] })
    },
  })

  const retryMutation = useMutation({
    mutationFn: retryTrainingJob,
    onSuccess: (newJob) => {
      getMessageInstance()?.success('重试任务已创建')
      navigate(`/training-jobs/${newJob.id}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteTrainingJob,
    onSuccess: () => {
      getMessageInstance()?.success('任务已删除')
      navigate('/training-jobs')
    },
  })

  const registerMutation = useMutation({
    mutationFn: registerModel,
    onSuccess: () => {
      getMessageInstance()?.success('模型注册成功')
      setRegisterModalOpen(false)
      setModelName('')
      setModelDesc('')
      setSelectedPaths([])
    },
  })

  // Pod list query (for distributed training)
  const { data: pods } = useQuery({
    queryKey: ['trainingJobPods', id],
    queryFn: () => getTrainingJobPods(id!),
    enabled: !!id && !!job?.vcjobName && activeTab === 'logs',
  })

  // History logs query (for completed jobs)
  const { data: logData, isLoading: logsLoading } = useQuery({
    queryKey: ['trainingJobLogs', id, selectedPod],
    queryFn: () =>
      getTrainingJobLogs(id!, {
        podName: selectedPod,
        tailLines: 2000,
      }),
    enabled: !!id && activeTab === 'logs' && !!job?.status && HISTORY_STATUSES.includes(job.status),
  })

  // GPU metrics query with polling
  const isRunning = job?.status === 'running'
  const { data: metricsData, isLoading: metricsLoading } = useQuery({
    queryKey: ['trainingJobMetrics', id],
    queryFn: () => getTrainingJobMetrics(id!),
    enabled: !!id && activeTab === 'metrics' && !!job?.status,
    refetchInterval: isRunning ? 10_000 : false,
  })

  const { shouldWarnGpu } = useGpuAlerts(
    metricsData?.gpuMetrics ?? [],
    metricsData?.gpuUtilizationHistory ?? [],
    { warningWindowMs: 10 * 60 * 1000 },
  )

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (error || !job) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <p>训练任务不存在或已被删除</p>
        <Link to="/training-jobs">返回任务列表</Link>
      </div>
    )
  }

  const statusCfg = TRAINING_JOB_STATUS_CONFIG[job.status] || { color: 'default', text: job.status }
  const hpEntries = job.hyperparameters ? Object.entries(job.hyperparameters) : []
  const isStreamable = STREAMABLE_STATUSES.includes(job.status)
  const isNotStarted = NOT_STARTED_STATUSES.includes(job.status)
  const isDistributed = (pods?.length ?? 0) > 1

  // Build WS URL for streaming mode (同源 Cookie 鉴权)
  const streamUrl =
    isStreamable && id ? buildLogStreamWsUrl(id, { podName: selectedPod, tailLines: 100 }) : null

  const logTabContent = (() => {
    if (isNotStarted) {
      return (
        <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
          任务尚未开始，日志将在启动后展示
        </div>
      )
    }

    if (isStreamable) {
      return (
        <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
          {isDistributed && (
            <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0', flexShrink: 0 }}>
              <Select
                size="small"
                value={selectedPod || pods?.[0]?.podName}
                onChange={setSelectedPod}
                style={{ width: 260 }}
                options={pods?.map((p) => ({
                  label: `${p.role} (${p.status === 'running' ? '运行中' : p.status})`,
                  value: p.podName,
                }))}
              />
            </div>
          )}
          <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
            <LogStream
              streamUrl={streamUrl}
              streamable
              emptyText="等待日志输出..."
              downloadName={job.name}
            />
          </div>
        </div>
      )
    }

    // History mode (succeeded/failed/stopped)
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        {isDistributed && (
          <div style={{ padding: '8px 12px', borderBottom: '1px solid #f0f0f0', flexShrink: 0 }}>
            <Select
              size="small"
              value={selectedPod || pods?.[0]?.podName}
              onChange={setSelectedPod}
              style={{ width: 260 }}
              options={pods?.map((p) => ({
                label: `${p.role} (${p.status})`,
                value: p.podName,
              }))}
            />
          </div>
        )}
        <div style={{ flex: 1, position: 'relative', minHeight: 0 }}>
          <LogStream
            initialLines={logData?.lines}
            loading={logsLoading}
            streamable={false}
            emptyText="暂无历史日志"
            downloadName={job.name}
          />
        </div>
      </div>
    )
  })()

  const metricsTabContent = (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 16,
        height: '100%',
        overflow: 'auto',
        minHeight: 0,
      }}
    >
      {/* GPU low utilization warning */}
      {shouldWarnGpu && (
        <Alert
          type="warning"
          showIcon
          message="GPU 利用率持续低于 10%，请检查训练脚本是否存在瓶颈"
        />
      )}

      {/* TensorBoard 可视化入口: 仅作业启用了 TensorBoard 时显示 */}
      {job.tensorboardEnabled && metricsData?.metricsUrl ? (
        <Card
          size="small"
          hoverable
          style={{ cursor: 'pointer' }}
          onClick={() => window.open(metricsData.metricsUrl!, '_blank')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <DesktopOutlined style={{ fontSize: 24, color: '#722ed1' }} />
            <div>
              <Typography.Text strong>打开 TensorBoard</Typography.Text>
              <br />
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                {metricsData.metricsUrl}
              </Typography.Text>
            </div>
          </div>
        </Card>
      ) : (
        !metricsLoading && (
          <Card size="small">
            <Typography.Text type="secondary">
              如需 TensorBoard 可视化请在创建训练任务时勾选「TensorBoard 可视化」开关
            </Typography.Text>
          </Card>
        )
      )}

      {/* GPU Metrics Chart */}
      <GpuMetricsChart
        gpuMetrics={metricsData?.gpuMetrics ?? []}
        gpuUtilizationHistory={metricsData?.gpuUtilizationHistory ?? []}
        loading={metricsLoading}
        prometheusAvailable={metricsData?.prometheusAvailable ?? false}
      />
    </div>
  )

  // --- Config Tab Content ---
  const configTabContent = (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 24,
        height: '100%',
        overflow: 'auto',
        minHeight: 0,
      }}
    >
      <Card title="启动命令" size="small">
        <Typography.Text copyable code style={{ fontSize: 12, wordBreak: 'break-all' }}>
          {job.command}
        </Typography.Text>
      </Card>

      <Card
        title={
          <Space>
            超参数
            <Tooltip title="这些参数作为环境变量原样注入容器。训练脚本可通过 os.environ 读取，通常用于 mlflow.log_params()。实际记录的超参数请查看实验追踪。">
              <Tag style={{ cursor: 'help' }}>环境变量</Tag>
            </Tooltip>
          </Space>
        }
        size="small"
        extra={
          job.mlflowEnabled && job.experimentId ? (
            <Button
              type="link"
              size="small"
              style={{ padding: 0 }}
              onClick={() => handleTabChange('experiment')}
            >
              查看实验 →
            </Button>
          ) : null
        }
      >
        {hpEntries.length > 0 ? (
          <Descriptions bordered size="small" column={2}>
            {hpEntries.map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                {value}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : (
          <Typography.Text type="secondary">未设置</Typography.Text>
        )}
      </Card>

      <Card title="数据集与镜像" size="small">
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="数据集">
            {job.datasetId ? (
              <Link to={`/datasets/${job.datasetId}`}>查看数据集详情</Link>
            ) : (
              <Typography.Text type="secondary">未挂载</Typography.Text>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="镜像">
            {job.imageId ? <Link to={`/images/${job.imageId}`}>查看镜像详情</Link> : '—'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="资源规格" size="small">
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="GPU">
            {job.gpuCount} 张（{job.gpuMode === 'exclusive' ? '独占' : '共享'}）
          </Descriptions.Item>
          <Descriptions.Item label="Worker 数量">
            {job.workerCount > 1 ? (
              <span>
                {job.workerCount} <Tag color="blue">分布式训练</Tag>
              </span>
            ) : (
              '1（单机）'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="CPU">{job.cpu} 核</Descriptions.Item>
          <Descriptions.Item label="内存">{job.memory}</Descriptions.Item>
          <Descriptions.Item label="优先级">
            {job.priority === 'high' ? '高' : job.priority === 'low' ? '低' : '普通'}
          </Descriptions.Item>
          <Descriptions.Item label="MLflow 追踪">
            {job.mlflowEnabled ? (
              job.experimentId ? (
                <Space size={4}>
                  <Tag color="green">已启用</Tag>
                  <Button
                    type="link"
                    size="small"
                    style={{ padding: 0 }}
                    onClick={() => handleTabChange('experiment')}
                  >
                    查看实验 →
                  </Button>
                </Space>
              ) : (
                <Tag color="green">已启用</Tag>
              )
            ) : (
              <Tag>未启用</Tag>
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  )

  const tabs = [
    {
      key: 'overview',
      label: '概览',
      children: (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 24,
            height: '100%',
            overflow: 'auto',
            minHeight: 0,
          }}
        >
          <Card title="状态" size="small">
            <Steps
              current={getStepIndex(job.status)}
              status={getStepStatus(job.status)}
              items={STATUS_STEPS.map((s) => ({ title: s.title }))}
            />
            {job.status === 'failed' && job.errorMessage && (
              <Alert
                type="error"
                showIcon
                style={{ marginTop: 16 }}
                message="失败原因"
                description={
                  <div>
                    <div>{job.errorMessage}</div>
                    <Button
                      type="link"
                      size="small"
                      style={{ padding: 0, marginTop: 8 }}
                      onClick={() => handleTabChange('logs')}
                    >
                      查看日志 →
                    </Button>
                  </div>
                }
              />
            )}
            {(job.status === 'failed' || job.status === 'stopped') && canWrite && (
              <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
                <Button
                  type="primary"
                  loading={retryMutation.isPending}
                  onClick={() => retryMutation.mutate(id!)}
                >
                  重新训练
                </Button>
              </div>
            )}
          </Card>

          {/* Success guidance card */}
          {job.status === 'succeeded' && (
            <Card
              size="small"
              style={{
                borderColor: '#52c41a',
                background: 'linear-gradient(135deg, #f6ffed 0%, #fcffe6 100%)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
                <CheckCircleOutlined style={{ fontSize: 24, color: '#52c41a' }} />
                <div>
                  <Typography.Text strong style={{ fontSize: 16 }}>
                    训练完成！
                  </Typography.Text>
                  <br />
                  <Typography.Text type="secondary">下一步建议：</Typography.Text>
                </div>
              </div>
              <Space>
                {canWriteModels && (
                  <Button
                    icon={<InboxOutlined />}
                    onClick={() => {
                      setModelName(`${job.name}-model`)
                      setRegisterModalOpen(true)
                    }}
                  >
                    注册模型到仓库
                  </Button>
                )}
                <Button icon={<RocketOutlined />} onClick={() => navigate('/models')}>
                  查看模型仓库
                </Button>
              </Space>
            </Card>
          )}

          {job.workspacePath && (
            <Card
              title="存储挂载"
              size="small"
              extra={
                job.status === 'succeeded' &&
                canWriteModels && (
                  <Button
                    type="primary"
                    icon={<InboxOutlined />}
                    size="small"
                    onClick={() => {
                      setModelName(`${job.name}-model`)
                      setRegisterModalOpen(true)
                    }}
                  >
                    注册模型到仓库
                  </Button>
                )
              }
            >
              <Descriptions bordered size="small" column={2}>
                <Descriptions.Item label={job.workspacePath}>
                  <Space>
                    <Tag color="blue">租户工作空间 (共享)</Tag>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      训练输出持久保存
                    </Typography.Text>
                  </Space>
                </Descriptions.Item>
                {job.homePath && (
                  <Descriptions.Item label={job.homePath}>
                    <Space>
                      <Tag color="green">个人目录</Tag>
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        仅本人可见
                      </Typography.Text>
                    </Space>
                  </Descriptions.Item>
                )}
              </Descriptions>
            </Card>
          )}

          <Card title="基本信息" size="small">
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="任务名称">{job.name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>
                {job.description || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDate(job.createdAt)}</Descriptions.Item>
              <Descriptions.Item label="运行时长">
                {formatDuration(job.startedAt, job.finishedAt)}
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                {job.source === 'manual' ? (
                  <Tag>手动创建</Tag>
                ) : job.source === 'dev_environment' ? (
                  <Tag color="blue">开发环境</Tag>
                ) : job.source === 'experiment_reproduction' ? (
                  <Tag color="green">实验复现</Tag>
                ) : job.source === 'tuning' && job.tuningStudyId ? (
                  <Link to={`/tuning/${job.tuningStudyId}`}>
                    <Tag color="purple" style={{ cursor: 'pointer' }}>
                      超参调优 · 返回调优详情
                    </Tag>
                  </Link>
                ) : null}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          {/* 实验追踪入口：仅 MLflow 启用且有关联 experiment 时显示, 点击切换到实验 Tab */}
          {job.mlflowEnabled && job.experimentId && (
            <Card
              size="small"
              hoverable
              style={{ cursor: 'pointer', borderColor: '#1890ff' }}
              onClick={() => handleTabChange('experiment')}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <ExperimentOutlined style={{ fontSize: 24, color: '#1890ff' }} />
                <div>
                  <Typography.Text strong>实验追踪</Typography.Text>
                  <br />
                  <Typography.Text type="secondary">
                    查看实验结果：超参数、指标曲线 →
                  </Typography.Text>
                </div>
              </div>
            </Card>
          )}

          {/* 实验追踪提示：仅 MLflow 启用但实验尚未创建时显示 */}
          {job.mlflowEnabled &&
            !job.experimentId &&
            ['running', 'queued', 'pending', 'initializing'].includes(job.status) && (
              <Card size="small" style={{ borderColor: '#faad14' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <ExperimentOutlined style={{ fontSize: 24, color: '#faad14' }} />
                  <Typography.Text type="secondary">
                    实验追踪正在初始化，任务开始运行后将自动创建实验记录
                  </Typography.Text>
                </div>
              </Card>
            )}
        </div>
      ),
    },
    // 实验 Tab: 内嵌实验追踪 (超参数/指标曲线/MLflow), 有关联实验时显示
    ...(job.experimentId
      ? [
          {
            key: 'experiment',
            label: '实验',
            children: <ExperimentPanel experimentId={job.experimentId} />,
          },
        ]
      : []),
    {
      key: 'logs',
      label: '日志',
      disabled: false,
      children: logTabContent,
    },
    {
      key: 'metrics',
      label: '指标',
      children: metricsTabContent,
    },
    {
      key: 'config',
      label: '配置',
      children: configTabContent,
    },
  ]

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        // 视口减固定 header 与内容区内边距(24×2),使详情页占满剩余高度
        height: 'calc(100vh - var(--kubeai-header-h) - 48px)',
        minHeight: 0,
      }}
    >
      <div style={{ flexShrink: 0 }}>
        <Breadcrumb
          items={[{ title: <Link to="/training-jobs">训练任务</Link> }, { title: job.name }]}
        />
      </div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          margin: '16px 0',
          flexShrink: 0,
        }}
      >
        <h2 style={{ margin: 0 }}>{job.name}</h2>
        <Space>
          <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>
            刷新状态
          </Button>
          {canWrite && ['running', 'queued', 'pending'].includes(job.status) && (
            <Popconfirm
              title="确认停止该训练任务？"
              description="运行中的训练将被终止"
              onConfirm={() => stopMutation.mutate(id!)}
              okText="确认"
              cancelText="取消"
            >
              <Button danger loading={stopMutation.isPending}>
                停止任务
              </Button>
            </Popconfirm>
          )}
          {canWrite && ['succeeded', 'failed', 'stopped'].includes(job.status) && (
            <Popconfirm
              title="确认删除该任务？"
              description="删除后将无法恢复"
              onConfirm={() => deleteMutation.mutate(id!)}
              okText="确认"
              cancelText="取消"
            >
              <Button danger loading={deleteMutation.isPending}>
                删除任务
              </Button>
            </Popconfirm>
          )}
        </Space>
      </div>
      {/* 深链 tab=experiment 但任务无实验时回退概览 */}
      <Tabs
        activeKey={activeTab === 'experiment' && !job.experimentId ? 'overview' : activeTab}
        onChange={handleTabChange}
        items={tabs}
        className="training-detail-tabs"
      />

      <Modal
        title="注册模型"
        open={registerModalOpen}
        onCancel={() => setRegisterModalOpen(false)}
        onOk={() => {
          if (!selectedPaths.length) {
            getMessageInstance()?.warning('请至少勾选一个文件或目录')
            return
          }
          registerMutation.mutate({
            name: modelName,
            description: modelDesc || undefined,
            filePaths: selectedPaths,
            trainingJobId: id,
          })
        }}
        confirmLoading={registerMutation.isPending}
        okText="确认注册"
        cancelText="取消"
        width={680}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div>
            <Typography.Text strong>模型名称</Typography.Text>
            <Input
              value={modelName}
              onChange={(e) => setModelName(e.target.value)}
              placeholder="例如 my-exp-model"
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Typography.Text strong>描述</Typography.Text>
            <Input
              value={modelDesc}
              onChange={(e) => setModelDesc(e.target.value)}
              placeholder="训练实验描述（可选）"
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Typography.Text strong>选择模型文件或目录</Typography.Text>
            <div style={{ marginTop: 4 }}>
              <FileBrowser value={selectedPaths} onChange={setSelectedPaths} roots={browserRoots} />
            </div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              仅允许浏览个人目录 <code>/kubeai/home/&lt;自己&gt;</code> 与当前租户工作空间{' '}
              <code>/kubeai/workspace/&lt;当前租户&gt;</code>; 注册时目录会按子树整体复制。
            </Typography.Text>
          </div>
          <div>
            <Typography.Text strong>关联训练任务:</Typography.Text> <Tag color="blue">当前任务</Tag>
          </div>
        </div>
      </Modal>
    </div>
  )
}
