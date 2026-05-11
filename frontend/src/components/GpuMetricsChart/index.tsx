import { useMemo } from 'react'
import { Card, Col, Row, Statistic } from 'antd'
import { Line } from '@ant-design/charts'
import type { TimeSeriesPoint } from '@/types/training-job'

interface GpuMetricPoint {
  gpuIndex: number
  utilizationPercent: number
  memoryUsedMib: number
  memoryTotalMib: number
  temperatureC: number
  powerW: number
}

interface GpuMetricsChartProps {
  gpuMetrics: GpuMetricPoint[]
  gpuUtilizationHistory: TimeSeriesPoint[]
  loading?: boolean
}

export default function GpuMetricsChart({
  gpuMetrics,
  gpuUtilizationHistory,
  loading,
}: GpuMetricsChartProps) {
  // Transform history data for chart
  const chartData = useMemo(() => {
    if (!gpuUtilizationHistory.length) return []
    return gpuUtilizationHistory.map((p) => ({
      time: new Date(p.timestamp).toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      }),
      gpu: p.label,
      value: p.value,
    }))
  }, [gpuUtilizationHistory])

  const lineConfig = {
    data: chartData,
    xField: 'time',
    yField: 'value',
    colorField: 'gpu',
    yAxis: {
      min: 0,
      max: 100,
      title: { text: '利用率 (%)' },
    },
    smooth: true,
    animation: false,
  }

  // Use first GPU for summary cards
  const gpu0 = gpuMetrics[0]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* GPU Summary Cards */}
      {gpuMetrics.length > 0 && (
        <Row gutter={16}>
          <Col span={6}>
            <Card size="small" loading={loading}>
              <Statistic
                title="GPU 利用率"
                value={gpu0?.utilizationPercent ?? 0}
                suffix="%"
                valueStyle={{ fontVariantNumeric: 'tabular-nums' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" loading={loading}>
              <Statistic
                title="显存使用"
                value={gpu0?.memoryUsedMib ?? 0}
                suffix={`/ ${gpu0?.memoryTotalMib ?? 0} MiB`}
                valueStyle={{ fontVariantNumeric: 'tabular-nums' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" loading={loading}>
              <Statistic
                title="温度"
                value={gpu0?.temperatureC ?? 0}
                suffix="°C"
                valueStyle={{ fontVariantNumeric: 'tabular-nums' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small" loading={loading}>
              <Statistic
                title="功耗"
                value={gpu0?.powerW ?? 0}
                suffix="W"
                valueStyle={{ fontVariantNumeric: 'tabular-nums' }}
              />
            </Card>
          </Col>
        </Row>
      )}

      {/* GPU Utilization Chart */}
      {chartData.length > 0 ? (
        <Card title="GPU 利用率趋势" size="small" loading={loading}>
          <Line {...lineConfig} />
        </Card>
      ) : (
        !loading && (
          <Card size="small">
            <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
              GPU 监控数据暂不可用
            </div>
          </Card>
        )
      )}
    </div>
  )
}
