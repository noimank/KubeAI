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
  Typography,
} from 'antd'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ExperimentOutlined, RocketOutlined } from '@ant-design/icons'
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
              <Link to={`/training-jobs/${experiment.trainingJobId}`}>
                {experiment.trainingJobName || '查看任务'}
              </Link>
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

      {/* Key metrics summary */}
      {experiment.metrics && experiment.metrics.length > 0 && (
        <Card title="关键指标" size="small">
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
        <Empty description="暂无超参数数据。请确认训练脚本通过环境变量 MLFLOW_RUN_ID 恢复了平台预创建的运行" />
      )}
    </Card>
  )

  const metricsTab = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {metricKeys.length === 0 ? (
        <Empty description="暂无指标数据。请确认训练脚本通过环境变量 MLFLOW_RUN_ID 恢复了平台预创建的运行" />
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

  const configTab = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <Card title="训练命令" size="small">
        {experiment.trainingJob?.command ? (
          <Typography.Text copyable code style={{ fontSize: 12, wordBreak: 'break-all' }}>
            {experiment.trainingJob.command}
          </Typography.Text>
        ) : (
          <Typography.Text type="secondary">—</Typography.Text>
        )}
      </Card>

      <Card title="资源规格" size="small">
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="GPU">
            {experiment.trainingJob?.gpuCount ?? '—'} 张
          </Descriptions.Item>
          <Descriptions.Item label="CPU">{experiment.trainingJob?.cpu ?? '—'} 核</Descriptions.Item>
          <Descriptions.Item label="内存">
            {experiment.trainingJob?.memory ?? '—'}
          </Descriptions.Item>
          <Descriptions.Item label="镜像">
            {experiment.trainingJob?.imageName || experiment.imageName || '—'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="数据集信息" size="small">
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="数据集版本">
            {experiment.trainingJob?.datasetVersion || experiment.datasetVersion || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="数据集">
            {experiment.trainingJobId ? (
              <Link to={`/training-jobs/${experiment.trainingJobId}`}>查看训练任务</Link>
            ) : (
              '—'
            )}
          </Descriptions.Item>
        </Descriptions>
      </Card>
    </div>
  )

  const tabs = [
    { key: 'overview', label: '概览', children: overviewTab },
    { key: 'hyperparams', label: '超参数', children: hyperparamsTab },
    { key: 'metrics', label: '指标', children: metricsTab },
    { key: 'config', label: '训练配置', children: configTab },
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
