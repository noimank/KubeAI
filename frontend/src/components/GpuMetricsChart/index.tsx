import { useMemo } from 'react'
import { Card, Col, Row, Statistic, Tooltip } from 'antd'
import { Line } from '@ant-design/charts'
import type { GpuMetricPoint, TimeSeriesPoint } from '@/types/metrics'
import {
  aggregateGpuUtilization,
  aggregateMemoryUsage,
  maxGpuTemperature,
  totalGpuPower,
} from '@/types/metrics'

interface GpuMetricsChartProps {
  gpuMetrics: GpuMetricPoint[]
  gpuUtilizationHistory: TimeSeriesPoint[]
  loading?: boolean
  /** When true, shows "Prometheus 未连接" hint instead of empty chart. */
  prometheusAvailable?: boolean
}

const CHART_HEIGHT = 260

export default function GpuMetricsChart({
  gpuMetrics,
  gpuUtilizationHistory,
  loading,
  prometheusAvailable = true,
}: GpuMetricsChartProps) {
  const gpuCount = gpuMetrics.length

  // Aggregate stats for summary cards
  const avgUtil = useMemo(() => aggregateGpuUtilization(gpuMetrics), [gpuMetrics])
  const { used: memUsed, total: memTotal } = useMemo(
    () => aggregateMemoryUsage(gpuMetrics),
    [gpuMetrics],
  )
  const maxTemp = useMemo(() => maxGpuTemperature(gpuMetrics), [gpuMetrics])
  const totalPower = useMemo(() => totalGpuPower(gpuMetrics), [gpuMetrics])

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
    height: CHART_HEIGHT,
    yAxis: {
      min: 0,
      max: 100,
      title: { text: '利用率 (%)' },
    },
    smooth: true,
    animation: false,
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      {/* GPU Summary Cards */}
      {gpuMetrics.length > 0 && (
        <Row gutter={16}>
          <Col xs={12} sm={6}>
            <Card size="small" loading={loading}>
              <Statistic
                title={
                  <Tooltip title={gpuCount > 1 ? `${gpuCount} 张 GPU 平均` : undefined}>
                    GPU 利用率
                  </Tooltip>
                }
                value={avgUtil}
                precision={1}
                suffix="%"
                valueStyle={{ fontVariantNumeric: 'tabular-nums' }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small" loading={loading}>
              <Statistic
                title={
                  <Tooltip title={gpuCount > 1 ? `${gpuCount} 张 GPU 合计` : undefined}>
                    显存使用
                  </Tooltip>
                }
                value={memUsed}
                precision={0}
                suffix={`/ ${memTotal.toFixed(0)} MiB`}
                valueStyle={{ fontVariantNumeric: 'tabular-nums' }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small" loading={loading}>
              <Statistic
                title="温度"
                value={maxTemp}
                precision={1}
                suffix="°C"
                valueStyle={{
                  fontVariantNumeric: 'tabular-nums',
                  color: maxTemp > 80 ? '#ff4d4f' : undefined,
                }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={6}>
            <Card size="small" loading={loading}>
              <Statistic
                title="功耗"
                value={totalPower}
                precision={1}
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
              {prometheusAvailable
                ? 'GPU 监控数据暂不可用'
                : '未连接 Prometheus，GPU 监控数据不可用'}
            </div>
          </Card>
        )
      )}

      {/* Per-GPU detail table (shown when >1 GPU) */}
      {gpuMetrics.length > 1 && (
        <Card size="small" title="GPU 详情">
          <table style={{ width: '100%', fontSize: 13, borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #f0f0f0' }}>
                {['GPU', '利用率', '显存', '温度', '功耗'].map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: '4px 8px',
                      textAlign: 'left',
                      fontWeight: 500,
                      color: '#999',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {gpuMetrics.map((g) => (
                <tr key={g.gpuIndex} style={{ borderBottom: '1px solid #f5f5f5' }}>
                  <td style={{ padding: '6px 8px' }}>GPU {g.gpuIndex}</td>
                  <td style={{ padding: '6px 8px' }}>{g.utilizationPercent.toFixed(1)}%</td>
                  <td style={{ padding: '6px 8px' }}>
                    {g.memoryUsedMib.toFixed(0)} / {g.memoryTotalMib.toFixed(0)} MiB
                  </td>
                  <td
                    style={{
                      padding: '6px 8px',
                      color: g.temperatureC > 80 ? '#ff4d4f' : undefined,
                    }}
                  >
                    {g.temperatureC.toFixed(1)}°C
                  </td>
                  <td style={{ padding: '6px 8px' }}>{g.powerW.toFixed(1)} W</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}
