import { Alert, Card, Spin, Table, Tag, Tooltip, Typography } from 'antd'
import type { InferenceServiceEvent } from '@/types/inference'
import { formatDate } from '@/utils/format'
import type { GpuMetricPoint, TimeSeriesPoint } from '@/types/metrics'
import GpuMetricsChart from '@/components/GpuMetricsChart'
import { useGpuAlerts } from '@/hooks/useGpuAlerts'

interface MonitorTabProps {
  serviceStatus: string
  events: InferenceServiceEvent[]
  eventsLoading: boolean
  gpuMetrics: GpuMetricPoint[]
  gpuUtilizationHistory: TimeSeriesPoint[]
  metricsLoading: boolean
  prometheusAvailable: boolean
}

export function MonitorTab({
  serviceStatus,
  events,
  eventsLoading,
  gpuMetrics,
  gpuUtilizationHistory,
  metricsLoading,
  prometheusAvailable,
}: MonitorTabProps) {
  const isServiceActive = serviceStatus === 'running' || serviceStatus === 'deploying'
  const healthyStatus = serviceStatus === 'running'

  const { shouldWarnGpu, shouldWarnTemp } = useGpuAlerts(gpuMetrics, gpuUtilizationHistory)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* 服务健康状态卡片 */}
      <Card size="small" title="服务健康状态">
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <Tag
            color={healthyStatus ? 'success' : 'warning'}
            style={{ fontSize: 14, padding: '4px 12px' }}
          >
            {healthyStatus ? '健康' : '异常'}
          </Tag>
          <Typography.Text type="secondary">
            {healthyStatus
              ? '推理服务运行正常，可接收请求'
              : isServiceActive
                ? '服务正在部署中，请稍候...'
                : '服务当前未运行'}
          </Typography.Text>
        </div>
      </Card>

      {/* GPU 低利用率告警 */}
      {shouldWarnGpu && (
        <Alert
          type="warning"
          message="GPU 利用率偏低"
          description="GPU 利用率持续低于阈值，请检查推理服务是否正常接收请求"
          showIcon
        />
      )}

      {/* GPU 高温告警 */}
      {shouldWarnTemp && (
        <Alert
          type="warning"
          message="GPU 温度过高"
          description="部分 GPU 温度已达到阈值，请检查散热环境或降低负载"
          showIcon
        />
      )}

      {/* Prometheus 降级信息 */}
      {!prometheusAvailable && (
        <Alert
          type="info"
          message="完整监控指标需配置 Prometheus"
          description="配置 Prometheus 后可在下方查看 GPU 利用率、显存、温度等详细指标"
          showIcon
        />
      )}

      {/* GPU 指标图表 */}
      {healthyStatus && (
        <GpuMetricsChart
          gpuMetrics={gpuMetrics}
          gpuUtilizationHistory={gpuUtilizationHistory}
          loading={metricsLoading}
          prometheusAvailable={prometheusAvailable}
        />
      )}

      {/* 事件日志表格 */}
      <Card size="small" title="事件日志">
        {eventsLoading ? (
          <div style={{ textAlign: 'center', padding: 32 }}>
            <Spin />
          </div>
        ) : events.length === 0 ? (
          <Typography.Text type="secondary">暂无事件记录</Typography.Text>
        ) : (
          <Table<InferenceServiceEvent>
            dataSource={events}
            rowKey={(record) => `${record.type}-${record.reason}-${record.lastTimestamp}`}
            size="small"
            pagination={{ pageSize: 10, size: 'small' }}
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
                render: (ts: string | null) => formatDate(ts),
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
    </div>
  )
}
