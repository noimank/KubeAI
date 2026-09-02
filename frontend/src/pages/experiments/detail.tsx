import { useMemo, useState } from 'react'
import {
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Empty,
  Space,
  Spin,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ExperimentOutlined, LinkOutlined, RocketOutlined } from '@ant-design/icons'
import { Line } from '@ant-design/charts'
import { useQuery } from '@tanstack/react-query'
import { getExperiment } from '@/services/experiments'
import { MLFLOW_UI_BASE_URL } from '@/config/mlflow'
import { formatDate } from '@/utils/format'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  active: { color: 'processing', text: '运行中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '已失败' },
}

function formatDuration(seconds: number | null): string {
  if (!seconds) return '—'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hours > 0) return `${hours}h ${minutes}m ${secs}s`
  if (minutes > 0) return `${minutes}m ${secs}s`
  return `${secs}s`
}

export default function ExperimentDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState('overview')

  const {
    data: experiment,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['experiment', id],
    queryFn: () => getExperiment(id!),
    enabled: !!id,
  })

  const metricKeys = useMemo(() => {
    if (!experiment?.metricHistories) return []
    return Object.keys(experiment.metricHistories)
  }, [experiment?.metricHistories])

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    )
  }

  if (error || !experiment) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <p>实验记录不存在或已被删除</p>
        <Link to="/experiments">返回实验列表</Link>
      </div>
    )
  }

  const statusCfg = STATUS_CONFIG[experiment.status] || {
    color: 'default',
    text: experiment.status,
  }
  const hpEntries = experiment.hyperparameters ? Object.entries(experiment.hyperparameters) : []

  const overviewTab = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="基本信息" size="small">
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="状态">
            <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="运行时长">
            {formatDuration(experiment.durationSeconds)}
          </Descriptions.Item>
          <Descriptions.Item label="训练任务">
            {experiment.trainingJobId ? (
              <Space>
                <Link to={`/training-jobs/${experiment.trainingJobId}`}>
                  {experiment.trainingJobName || '查看任务'}
                </Link>
                <Tooltip title="跳转至训练任务详情，查看完整配置、日志与资源信息">
                  <LinkOutlined style={{ color: '#1890ff' }} />
                </Tooltip>
              </Space>
            ) : (
              '—'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="数据集版本">
            {experiment.datasetVersion || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="镜像">
            {experiment.trainingJob?.imageName || experiment.imageName || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDate(experiment.createdAt)}</Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 关键超参数摘要 */}
      {hpEntries.length > 0 && (
        <Card
          title="关键超参数"
          size="small"
          extra={
            <Button type="link" size="small" onClick={() => setActiveTab('hyperparams')}>
              查看全部 →
            </Button>
          }
        >
          <Descriptions bordered size="small" column={2}>
            {hpEntries.slice(0, 6).map(([key, value]) => (
              <Descriptions.Item key={key} label={key}>
                <Typography.Text code style={{ fontSize: 12 }}>
                  {String(value)}
                </Typography.Text>
              </Descriptions.Item>
            ))}
          </Descriptions>
        </Card>
      )}

      {/* 关键指标摘要 */}
      {experiment.metrics && experiment.metrics.length > 0 && (
        <Card
          title="关键指标"
          size="small"
          extra={
            <Button type="link" size="small" onClick={() => setActiveTab('metrics')}>
              查看曲线 →
            </Button>
          }
        >
          <Descriptions bordered size="small" column={2}>
            {experiment.metrics.map((m) => (
              <Descriptions.Item key={m.key} label={m.key}>
                {typeof m.value === 'number' ? m.value.toFixed(6) : m.value}
              </Descriptions.Item>
            ))}
          </Descriptions>
        </Card>
      )}
    </div>
  )

  const hyperparamsTab = (
    <Card title="超参数" size="small">
      <Typography.Text
        type="secondary"
        style={{ display: 'block', marginBottom: 16, fontSize: 12 }}
      >
        训练脚本通过 mlflow.log_params()
        记录的实际超参数。若与创建任务时配置的初始值不同，以此处为准。
      </Typography.Text>
      {hpEntries.length > 0 ? (
        <Descriptions bordered size="small" column={2}>
          {hpEntries.map(([key, value]) => (
            <Descriptions.Item key={key} label={key}>
              <Typography.Text code copyable style={{ fontSize: 12 }}>
                {String(value)}
              </Typography.Text>
            </Descriptions.Item>
          ))}
        </Descriptions>
      ) : (
        <Empty description="训练脚本未记录超参数。请确保脚本中调用了 mlflow.log_params()" />
      )}
    </Card>
  )

  const metricsTab = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {metricKeys.length === 0 ? (
        <Empty description="训练脚本未记录指标。请确保脚本中调用了 mlflow.log_metric()" />
      ) : (
        metricKeys.map((key) => {
          const series = experiment.metricHistories?.[key] ?? []
          const chartData = series.map((p) => ({
            step: p.step,
            value: p.value,
          }))
          return (
            <Card key={key} title={key} size="small">
              {chartData.length > 0 ? (
                <Line
                  data={chartData}
                  xField="step"
                  yField="value"
                  shapeField="smooth"
                  style={{ lineWidth: 2 }}
                  interaction={{
                    tooltip: {
                      marker: false,
                    },
                  }}
                />
              ) : (
                <Empty description="暂无数据" />
              )}
            </Card>
          )
        })
      )}
    </div>
  )

  const tabs = [
    { key: 'overview', label: '概览', children: overviewTab },
    { key: 'hyperparams', label: '超参数', children: hyperparamsTab },
    { key: 'metrics', label: '指标', children: metricsTab },
  ]

  return (
    <div style={{ padding: 0 }}>
      <Breadcrumb
        items={[
          { title: <Link to="/experiments">实验追踪</Link> },
          { title: experiment.trainingJobName || '实验详情' },
        ]}
      />
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          margin: '16px 0',
        }}
      >
        <h2 style={{ margin: 0 }}>{experiment.trainingJobName || '实验详情'}</h2>
        <Space>
          {experiment.mlflowExperimentId && (
            <Button
              icon={<ExperimentOutlined />}
              href={
                experiment.mlflowRunId
                  ? `${MLFLOW_UI_BASE_URL}/#/experiments/${experiment.mlflowExperimentId}/runs/${experiment.mlflowRunId}`
                  : `${MLFLOW_UI_BASE_URL}/#/experiments/${experiment.mlflowExperimentId}`
              }
              target="_blank"
              rel="noreferrer"
            >
              {experiment.mlflowRunId ? '在 MLflow UI 中查看本次运行' : '在 MLflow UI 中查看实验'}
            </Button>
          )}
          <Button
            icon={<RocketOutlined />}
            onClick={() => navigate(`/training-jobs/create?from_experiment=${id}`)}
          >
            复现实验
          </Button>
        </Space>
      </div>
      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabs} />
    </div>
  )
}
