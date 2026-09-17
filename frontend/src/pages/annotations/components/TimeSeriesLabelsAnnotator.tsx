import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, Card, Space, Tag, Typography } from 'antd'
import { UndoOutlined } from '@ant-design/icons'
import type { AnnotationTask } from '@/types/annotation'
import type { ConfigNode, LabelStudioControlConfig } from '../utils/parseLabelConfig'
import type { Region } from '../hooks/useAnnotationRegions'
import { regionsOf } from '../utils/regions'
import { labelColor } from './annotationColors'
import LabelPalette from './LabelPalette'
import TimeSeriesChart from './viewers/TimeSeriesChart'
import { getMessageInstance } from '@/utils/messageHolder'
import {
  fetchTimeSeriesText,
  isUrlValue,
  parseTimeSeriesData,
  type ParsedTimeSeries,
} from '../utils/timeSeries'
import { generateId } from '../utils/id'

interface TimeSeriesLabelsAnnotatorProps {
  task: AnnotationTask
  objectNode: ConfigNode
  controlConfig: LabelStudioControlConfig
  readOnly: boolean
  regions: Region[]
  selectedRegionId: string | null
  onAddRegion: (region: Region) => void
  onDeleteRegion: (id: string) => void
  onSelectRegion: (id: string | null) => void
}

/**
 * TimeSeriesLabels 标注器 —— 在时间序列图上点击两次定义一个区间（异常/事件标注）。
 * 第一次点击设起点（虚线标记），第二次点击设终点 → 创建 timeseries region。
 * perRegion 控件（如 Choices）通过侧栏挂载到选中的区间上。
 */
export default function TimeSeriesLabelsAnnotator({
  task,
  objectNode,
  controlConfig,
  readOnly = false,
  regions,
  selectedRegionId,
  onAddRegion,
  onDeleteRegion,
  onSelectRegion,
}: TimeSeriesLabelsAnnotatorProps) {
  const field = objectNode.field || 'ts'
  const sep = objectNode.attrs.sep
  const timeColumn = objectNode.attrs.timecolumn
  const channels = objectNode.channels
  const labels = useMemo(() => controlConfig.choices.map((c) => c.value), [controlConfig.choices])
  const [activeLabel, setActiveLabel] = useState<string | null>(labels[0] ?? null)
  const [data, setData] = useState<ParsedTimeSeries | null>(null)
  const [pendingStart, setPendingStart] = useState<number | null>(null)

  const tsRegions = useMemo(
    () => regionsOf(regions, controlConfig.name, 'timeseries'),
    [regions, controlConfig.name],
  )

  useEffect(() => {
    setActiveLabel(labels[0] ?? null)
    setPendingStart(null)
  }, [task.id, labels])

  // 加载数据
  useEffect(() => {
    let cancelled = false
    const raw = task.data?.[field]
    void (async () => {
      try {
        const source = isUrlValue(raw) ? await fetchTimeSeriesText(raw as string) : raw
        const parsed = parseTimeSeriesData(source, { sep, timeColumn })
        if (!cancelled) setData(parsed)
      } catch {
        if (!cancelled) setData(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [task.data, field, sep, timeColumn])

  const onTimeSelect = useCallback(
    (t: number) => {
      if (readOnly || !data) return
      if (pendingStart === null) {
        setPendingStart(t)
        return
      }
      if (!activeLabel) {
        getMessageInstance()?.warning('请先选择标签')
        setPendingStart(null)
        return
      }
      const start = Math.min(pendingStart, t)
      const end = Math.max(pendingStart, t)
      const instant =
        Math.abs(end - start) <
        (data.times.length > 1 ? Math.abs(data.times[1] - data.times[0]) / 2 : 0.001)
      onAddRegion({
        id: generateId(),
        fromName: controlConfig.name,
        label: activeLabel,
        value: { kind: 'timeseries', start, end, instant },
        perRegionResults: {},
      })
      setPendingStart(null)
    },
    [readOnly, data, pendingStart, activeLabel, controlConfig.name, onAddRegion],
  )

  const chartRegions = tsRegions.map((r, i) => ({
    start: r.value.start,
    end: r.value.end,
    color: `${labelColor(i)}33`,
  }))

  if (!data) {
    return <Typography.Text type="secondary">时间序列加载中…</Typography.Text>
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {!readOnly && (
        <>
          <LabelPalette labels={labels} activeLabel={activeLabel} onChange={setActiveLabel} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {pendingStart === null
              ? '点击图表选择区间起点，再点击选择终点'
              : '已选起点，点击选择终点（或点「取消」重选）'}
          </Typography.Text>
        </>
      )}

      <TimeSeriesChart
        data={data}
        channels={channels}
        regions={chartRegions}
        pendingSpan={pendingStart !== null ? { start: pendingStart, end: null } : null}
        readOnly={readOnly}
        onTimeSelect={onTimeSelect}
      />

      {!readOnly && pendingStart !== null && (
        <Button icon={<UndoOutlined />} size="small" onClick={() => setPendingStart(null)}>
          取消起点
        </Button>
      )}

      {tsRegions.length > 0 && (
        <Card size="small" title={`已标注区间 (${tsRegions.length})`}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {tsRegions.map((r, i) => (
              <Space key={r.id} style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space>
                  <Tag color={labelColor(i)}>{r.label}</Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {formatTime(r.value.start)} – {formatTime(r.value.end)}
                  </Typography.Text>
                </Space>
                <Space>
                  <Button
                    type="text"
                    size="small"
                    onClick={() => onSelectRegion(selectedRegionId === r.id ? null : r.id)}
                  >
                    {selectedRegionId === r.id ? '取消选择' : '选择'}
                  </Button>
                  {!readOnly && (
                    <Button type="text" size="small" danger onClick={() => onDeleteRegion(r.id)}>
                      删除
                    </Button>
                  )}
                </Space>
              </Space>
            ))}
          </Space>
        </Card>
      )}
    </Space>
  )
}

function formatTime(t: number): string {
  if (Math.abs(t) > 1e12) {
    // ms 时间戳
    return new Date(t).toLocaleString()
  }
  return String(Math.round(t * 100) / 100)
}
