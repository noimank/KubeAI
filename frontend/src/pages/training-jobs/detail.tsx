import { useMemo, useState } from 'react'
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Select,
  Spin,
  Steps,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import { Link, useParams } from 'react-router-dom'
import { DesktopOutlined, ReloadOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import LogStream from '@/components/LogStream'
import GpuMetricsChart from '@/components/GpuMetricsChart'
import {
  buildLogStreamUrl,
  getTrainingJob,
  getTrainingJobLogs,
  getTrainingJobMetrics,
  getTrainingJobPods,
} from '@/services/training-jobs'
import { ACCESS_TOKEN_KEY } from '@/stores/authStore'
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
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedPod, setSelectedPod] = useState<string | undefined>(undefined)

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
            {job.errorMessage && (
              <Typography.Text type="danger" style={{ marginTop: 12, display: 'block' }}>
                错误信息：{job.errorMessage}
              </Typography.Text>
            )}
          </Card>

          <Card title="基本参数" size="small">
            <Descriptions bordered size="small" column={2}>
              <Descriptions.Item label="任务名称">{job.name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="描述" span={2}>
                {job.description || '—'}
              </Descriptions.Item>
              <Descriptions.Item label="启动命令" span={2}>
                <Typography.Text copyable code style={{ fontSize: 12 }}>
                  {job.command}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">{job.createdAt}</Descriptions.Item>
              <Descriptions.Item label="运行时长">
                {formatDuration(job.startedAt, job.finishedAt)}
              </Descriptions.Item>
            </Descriptions>
          </Card>

          <Card title="资源配置" size="small">
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
              <Descriptions.Item label="优先级">
                {job.priority === 'high' ? '高' : job.priority === 'low' ? '低' : '普通'}
              </Descriptions.Item>
              <Descriptions.Item label="CPU">{job.cpu} 核</Descriptions.Item>
              <Descriptions.Item label="内存">{job.memory}</Descriptions.Item>
            </Descriptions>
          </Card>

          {hpEntries.length > 0 && (
            <Card title="超参数" size="small">
              <Descriptions bordered size="small" column={2}>
                {hpEntries.map(([key, value]) => (
                  <Descriptions.Item key={key} label={key}>
                    {value}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            </Card>
          )}
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
        <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>
          刷新状态
        </Button>
      </div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabs} />
    </div>
  )
}
