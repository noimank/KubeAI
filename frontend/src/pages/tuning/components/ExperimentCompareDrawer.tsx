import { useMemo, useState } from 'react'
import { Card, Descriptions, Drawer, Empty, Select, Spin, Table, Tabs, Tag, Tooltip } from 'antd'
import type { ColumnType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { Line } from '@ant-design/charts'
import { compareExperiments } from '@/services/experiments'
import type { ExperimentComparison } from '@/types/experiment'

interface Props {
  open: boolean
  experimentIds: string[]
  onClose: () => void
}

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  active: { color: 'processing', text: '运行中' },
  completed: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '已失败' },
}

export default function ExperimentCompareDrawer({ open, experimentIds, onClose }: Props) {
  const [activeTab, setActiveTab] = useState('hyperparams')
  const [selectedMetric, setSelectedMetric] = useState<string | undefined>()

  const { data: comparison, isLoading } = useQuery<ExperimentComparison | null>({
    queryKey: ['compareExperiments', experimentIds],
    queryFn: () => compareExperiments(experimentIds),
    enabled: open && experimentIds.length >= 2,
  })

  const metricKeys = useMemo(() => {
    if (!comparison) return []
    return comparison.metricsComparison.map((m) => m.metricKey)
  }, [comparison])

  const currentMetricData = useMemo(() => {
    if (!comparison) return null
    const key = selectedMetric || metricKeys[0]
    return comparison.metricsComparison.find((m) => m.metricKey === key) ?? null
  }, [comparison, selectedMetric, metricKeys])

  // Build experiment name lookup
  const expNameMap = useMemo(() => {
    const map: Record<string, string> = {}
    if (comparison) {
      for (const exp of comparison.experiments) {
        map[exp.id] = exp.trainingJobName || exp.id.slice(0, 8)
      }
    }
    return map
  }, [comparison])

  // Transform metric data for Line chart
  const chartData = useMemo(() => {
    if (!currentMetricData) return []
    const points: Array<{ experiment: string; step: number; value: number }> = []
    for (const [expId, series] of Object.entries(currentMetricData.series)) {
      for (const point of series) {
        points.push({
          experiment: expNameMap[expId] || expId.slice(0, 8),
          step: point.step,
          value: point.value,
        })
      }
    }
    return points
  }, [currentMetricData, expNameMap])

  const hyperparamColumns = useMemo(() => {
    if (!comparison) return []
    const cols: ColumnType<Record<string, unknown>>[] = [{ title: '超参数', dataIndex: 'key' }]
    for (const exp of comparison.experiments) {
      cols.push({
        title: <Tooltip title={exp.id}>{exp.trainingJobName || exp.id.slice(0, 8)}</Tooltip>,
        dataIndex: exp.id,
        render: (val: unknown) => (
          <span style={{ fontVariantNumeric: 'tabular-nums' }}>
            {val != null ? String(val) : '—'}
          </span>
        ),
      })
    }
    return cols
  }, [comparison])

  const hyperparamDataSource = useMemo(() => {
    if (!comparison) return []
    return comparison.hyperparamsDiff.map((diff) => {
      const row: Record<string, unknown> = { key: diff.key }
      for (const [expId, val] of Object.entries(diff.values)) {
        row[expId] = val ?? '—'
      }
      return row
    })
  }, [comparison])

  const getRowClassName = (record: Record<string, unknown>) => {
    // Find the HyperparamDiff for this row
    if (!comparison) return ''
    const diff = comparison.hyperparamsDiff.find((d) => d.key === record.key)
    return diff?.isDifferent ? 'bg-amber-50' : ''
  }

  return (
    <Drawer title="实验对比" open={open} onClose={onClose} width="90vw" destroyOnHidden>
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 80 }}>
          <Spin size="large" />
        </div>
      ) : !comparison ? (
        <Empty description="无法加载对比数据" />
      ) : (
        <>
          {/* Experiment summary cards */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 16, overflowX: 'auto' }}>
            {comparison.experiments.map((exp) => {
              const cfg = STATUS_CONFIG[exp.status] || { color: 'default', text: exp.status }
              return (
                <Card key={exp.id} size="small" style={{ minWidth: 200, flexShrink: 0 }}>
                  <div style={{ marginBottom: 8, fontWeight: 600 }}>{expNameMap[exp.id]}</div>
                  <Descriptions size="small" column={1} colon={false}>
                    <Descriptions.Item label="状态">
                      <Tag color={cfg.color}>{cfg.text}</Tag>
                    </Descriptions.Item>
                    {exp.metrics?.slice(0, 3).map((m) => (
                      <Descriptions.Item key={m.key} label={m.key}>
                        <span style={{ fontVariantNumeric: 'tabular-nums' }}>
                          {typeof m.value === 'number' ? m.value.toFixed(4) : m.value}
                        </span>
                      </Descriptions.Item>
                    ))}
                  </Descriptions>
                </Card>
              )
            })}
          </div>

          <Tabs
            activeKey={activeTab}
            onChange={setActiveTab}
            items={[
              {
                key: 'hyperparams',
                label: '超参数对比',
                children: (
                  <Table
                    rowKey="key"
                    columns={hyperparamColumns}
                    dataSource={hyperparamDataSource}
                    pagination={false}
                    size="small"
                    rowClassName={getRowClassName}
                    bordered
                  />
                ),
              },
              {
                key: 'metrics',
                label: '指标对比',
                children: (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {metricKeys.length === 0 ? (
                      <Empty description="暂无指标数据" />
                    ) : (
                      <>
                        <Select
                          value={selectedMetric || metricKeys[0]}
                          onChange={setSelectedMetric}
                          style={{ width: 240 }}
                          options={metricKeys.map((k) => ({ label: k, value: k }))}
                          placeholder="选择指标"
                        />
                        {chartData.length > 0 && (
                          <Line
                            data={chartData}
                            xField="step"
                            yField="value"
                            colorField="experiment"
                            shapeField="smooth"
                            style={{ lineWidth: 2 }}
                            interaction={{
                              tooltip: {
                                marker: false,
                              },
                            }}
                          />
                        )}
                      </>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </>
      )}
    </Drawer>
  )
}
