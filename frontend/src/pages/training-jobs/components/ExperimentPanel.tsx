import { useMemo } from 'react'
import { Button, Card, Descriptions, Empty, Space, Spin, Tag, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
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

interface Props {
  experimentId: string
}

/** 训练任务详情内嵌的实验面板: 基本信息 + 超参数 + 指标曲线 */
export default function ExperimentPanel({ experimentId }: Props) {
  const navigate = useNavigate()

  const {
    data: experiment,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['experiment', experimentId],
    queryFn: () => getExperiment(experimentId),
    enabled: !!experimentId,
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
    return <Empty description="实验记录不存在或已被删除" style={{ padding: 80 }} />
  }

  const statusCfg = STATUS_CONFIG[experiment.status] || {
    color: 'default',
    text: experiment.status,
  }
  const hpEntries = experiment.hyperparameters ? Object.entries(experiment.hyperparameters) : []

  return (
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
      <Card
        title="基本信息"
        size="small"
        extra={
          <Space>
            {experiment.mlflowExperimentId && (
              <Button
                size="small"
                icon={<ExperimentOutlined />}
                href={
                  experiment.mlflowRunId
                    ? `${MLFLOW_UI_BASE_URL}/#/experiments/${experiment.mlflowExperimentId}/runs/${experiment.mlflowRunId}`
                    : `${MLFLOW_UI_BASE_URL}/#/experiments/${experiment.mlflowExperimentId}`
                }
                target="_blank"
                rel="noreferrer"
              >
                {experiment.mlflowRunId ? 'MLflow UI 中查看本次运行' : 'MLflow UI 中查看实验'}
              </Button>
            )}
            <Button
              size="small"
              icon={<RocketOutlined />}
              onClick={() => navigate(`/training-jobs/create?from_experiment=${experimentId}`)}
            >
              复现实验
            </Button>
          </Space>
        }
      >
        <Descriptions bordered size="small" column={2}>
          <Descriptions.Item label="状态">
            <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label="运行时长">
            {formatDuration(experiment.durationSeconds)}
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

      <Card title="指标" size="small">
        {metricKeys.length === 0 ? (
          <Empty description="训练脚本未记录指标。请确保脚本中调用了 mlflow.log_metric()" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            {experiment.metrics && experiment.metrics.length > 0 && (
              <Descriptions bordered size="small" column={2}>
                {experiment.metrics.map((m) => (
                  <Descriptions.Item key={m.key} label={`${m.key} (最终值)`}>
                    {typeof m.value === 'number' ? m.value.toFixed(6) : m.value}
                  </Descriptions.Item>
                ))}
              </Descriptions>
            )}
            {metricKeys.map((key) => {
              const series = experiment.metricHistories?.[key] ?? []
              const chartData = series.map((p) => ({ step: p.step, value: p.value }))
              return (
                <div key={key}>
                  <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
                    {key}
                  </Typography.Text>
                  {chartData.length > 0 ? (
                    <Line
                      data={chartData}
                      xField="step"
                      yField="value"
                      shapeField="smooth"
                      style={{ lineWidth: 2 }}
                      interaction={{ tooltip: { marker: false } }}
                    />
                  ) : (
                    <Empty description="暂无数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                  )}
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </div>
  )
}
