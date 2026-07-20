import { useEffect, useState } from 'react'
import { Spin, Typography } from 'antd'
import TimeSeriesChart from './TimeSeriesChart'
import type { TimeSeriesChannel } from '../../utils/parseLabelConfig'
import {
  fetchTimeSeriesText,
  isUrlValue,
  parseTimeSeriesData,
  type ParsedTimeSeries,
} from '../../utils/timeSeries'

interface TimeSeriesViewerProps {
  value: unknown
  channels?: TimeSeriesChannel[]
  sep?: string
  timeColumn?: string
}

/** 加载并解析时间序列数据，渲染只读多通道折线图 */
export default function TimeSeriesViewer({
  value,
  channels,
  sep,
  timeColumn,
}: TimeSeriesViewerProps) {
  const [data, setData] = useState<ParsedTimeSeries | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLoading(true)
      setError(false)
      try {
        const raw = isUrlValue(value) ? await fetchTimeSeriesText(value as string) : value
        const parsed = parseTimeSeriesData(raw, { sep, timeColumn })
        if (!cancelled) setData(parsed)
      } catch {
        if (!cancelled) setError(true)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [value, sep, timeColumn])

  if (loading) {
    return (
      <div style={{ padding: 48, display: 'flex', justifyContent: 'center' }}>
        <Spin />
      </div>
    )
  }
  if (error || !data) {
    return <Typography.Text type="danger">时间序列加载失败</Typography.Text>
  }
  return <TimeSeriesChart data={data} channels={channels} readOnly />
}
