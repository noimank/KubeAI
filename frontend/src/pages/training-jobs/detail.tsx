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
  Typography,
} from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  CheckCircleOutlined,
  DesktopOutlined,
  InboxOutlined,
  RocketOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import LogStream from '@/components/LogStream'
import GpuMetricsChart from '@/components/GpuMetricsChart'
import { useRbacStore } from '@/stores/rbacStore'
import {
  buildLogStreamUrl,
  getTrainingJob,
  getTrainingJobLogs,
  getTrainingJobMetrics,
  getTrainingJobPods,
  stopTrainingJob,
  retryTrainingJob,
} from '@/services/training-jobs'
import { registerModel } from '@/services/models'
import { ACCESS_TOKEN_KEY } from '@/utils/constants'
import { getMessageInstance } from '@/utils/messageHolder'
import type { TrainingJobStatus } from '@/types/training-job'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '等待中' },
  queued: { color: 'warning', text: '排队中' },
  initializing: { color: 'processing', text: '初始化' },
  running: { color: 'processing', text: '运行中' },
  succeeded: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

const STATUS_STEPS = [
  { key: 'pending', title: '等待' },
  { key: 'queued', title: '排队' },
  { key: 'running', title: '运行' },
  { key: 'succeeded', title: '完成' },
]

const STREAMABLE_STATUSES: TrainingJobStatus[] = ['pending', 'queued', 'initializing', 'running']
const HISTORY_STATUSES: TrainingJobStatus[] = ['succeeded', 'failed', 'stopped']
const NOT_STARTED_STATUSES: TrainingJobStatus[] = ['pending', 'queued']

const LOW_GPU_THRESHOLD = 10
const WARNING_DURATION_MS = 10 * 60 * 1000

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
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedPod, setSelectedPod] = useState<string | undefined>(undefined)
  const [registerModalOpen, setRegisterModalOpen] = useState(false)
  const [modelName, setModelName] = useState('')
  const [modelDesc, setModelDesc] = useState('')
  const [modelFilePaths, setModelFilePaths] = useState('')
  const queryClient = useQueryClient()

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('training_jobs:write')
  const canWriteModels = hasPermission('models:write')

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

  const registerMutation = useMutation({
    mutationFn: registerModel,
    onSuccess: () => {
      getMessageInstance()?.success('模型注册成功，文件正在上传中')
      setRegisterModalOpen(false)
      setModelName('')
      setModelDesc('')
      setModelFilePaths('')
    },
    onError: () => {
      getMessageInstance()?.error('模型注册失败')
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

  // GPU low utilization warning
  const shouldWarnGpu = useMemo(() => {
    const history = metricsData?.gpuUtilizationHistory
    if (!history?.length) return false
    const cutoff = Date.now() - WARNING_DURATION_MS
    const recent = history.filter((p) => new Date(p.timestamp).getTime() >= cutoff)
    if (recent.length < 10) return false
    return recent.every((p) => p.value < LOW_GPU_THRESHOLD)
  }, [metricsData?.gpuUtilizationHistory])

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

  const statusCfg = STATUS_CONFIG[job.status] || { color: 'default', text: job.status }
  const hpEntries = job.hyperparameters ? Object.entries(job.hyperparameters) : []
  const isStreamable = STREAMABLE_STATUSES.includes(job.status)
  const isNotStarted = NOT_STARTED_STATUSES.includes(job.status)
  const isDistributed = (pods?.length ?? 0) > 1

  // Build SSE URL for streaming mode
  const token = typeof window !== 'undefined' ? localStorage.getItem(ACCESS_TOKEN_KEY) : ''
  const streamUrl =
    isStreamable && id && token
      ? buildLogStreamUrl(id, { podName: selectedPod, tailLines: 100 })
      : null

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
        <div style={{ height: 500, display: 'flex', flexDirection: 'column' }}>
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
          <div style={{ flex: 1, position: 'relative' }}>
            <LogStream streamUrl={streamUrl} streamable emptyText="等待日志输出..." />
          </div>
        </div>
      )
    }

    // History mode (succeeded/failed/stopped)
    return (
      <div style={{ height: 500, display: 'flex', flexDirection: 'column' }}>
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
        <div style={{ flex: 1, position: 'relative' }}>
          <LogStream
            initialLines={logData?.lines}
            loading={logsLoading}
            streamable={false}
            emptyText="暂无历史日志"
          />
        </div>
      </div>
    )
  })()

  const metricsTabContent = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* GPU low utilization warning */}
      {shouldWarnGpu && (
        <Alert
          type="warning"
          showIcon
          message="GPU 利用率持续低于 10%，请检查训练脚本是否存在瓶颈"
        />
      )}

      {/* Metrics URL entry point */}
      {metricsData?.metricsUrl ? (
        <Card
          size="small"
          hoverable
          style={{ cursor: 'pointer' }}
          onClick={() => window.open(metricsData.metricsUrl!, '_blank')}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <DesktopOutlined style={{ fontSize: 24, color: '#1890ff' }} />
            <div>
              <Typography.Text strong>打开训练指标面板</Typography.Text>
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
              如需查看 TensorBoard/MLflow，请在创建训练任务时配置指标端口
            </Typography.Text>
          </Card>
        )
      )}

      {/* GPU Metrics Chart */}
      <GpuMetricsChart
        gpuMetrics={metricsData?.gpuMetrics ?? []}
        gpuUtilizationHistory={metricsData?.gpuUtilizationHistory ?? []}
        loading={metricsLoading}
      />
    </div>
  )

  // --- Config Tab Content ---
  const configTabContent = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Card title="启动命令" size="small">
        <Typography.Text copyable code style={{ fontSize: 12, wordBreak: 'break-all' }}>
          {job.command}
        </Typography.Text>
      </Card>

      <Card title="超参数" size="small">
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
        </Descriptions>
      </Card>
    </div>
  )

  const tabs = [
    {
      key: 'overview',
      label: '概览',
      children: (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
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
                      onClick={() => setActiveTab('logs')}
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
                        跨租户共享
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
              <Descriptions.Item label="创建时间">{job.createdAt}</Descriptions.Item>
              <Descriptions.Item label="运行时长">
                {formatDuration(job.startedAt, job.finishedAt)}
              </Descriptions.Item>
              <Descriptions.Item label="来源">
                {job.source === 'dev_environment' ? (
                  <Tag color="blue">开发环境</Tag>
                ) : job.source === 'experiment_reproduction' ? (
                  <Tag color="green">实验复现</Tag>
                ) : (
                  <Tag>手动创建</Tag>
                )}
              </Descriptions.Item>
            </Descriptions>
          </Card>
        </div>
      ),
    },
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
    <div style={{ padding: 0 }}>
      <Breadcrumb
        items={[{ title: <Link to="/training-jobs">训练任务</Link> }, { title: job.name }]}
      />
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          margin: '16px 0',
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
        </Space>
      </div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabs} />

      <Modal
        title="注册模型"
        open={registerModalOpen}
        onCancel={() => setRegisterModalOpen(false)}
        onOk={() => {
          const filePaths = modelFilePaths
            .split('\n')
            .map((p) => p.trim())
            .filter(Boolean)
          if (!filePaths.length) {
            getMessageInstance()?.warning('请输入至少一个文件路径')
            return
          }
          registerMutation.mutate({
            name: modelName,
            description: modelDesc || undefined,
            filePaths,
            trainingJobId: id,
          })
        }}
        confirmLoading={registerMutation.isPending}
        okText="确认注册"
        cancelText="取消"
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
            <Typography.Text strong>工作空间文件路径（每行一个）</Typography.Text>
            <Input.TextArea
              value={modelFilePaths}
              onChange={(e) => setModelFilePaths(e.target.value)}
              placeholder={'experiment-1/model.pth\nexperiment-1/config.yaml'}
              rows={4}
              style={{ marginTop: 4, fontFamily: 'monospace' }}
            />
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              路径相对于 {job.workspacePath || '/workspace'} 目录
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
