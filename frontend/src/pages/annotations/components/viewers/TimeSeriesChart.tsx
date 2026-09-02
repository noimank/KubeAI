import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import type { ParsedTimeSeries } from '../../utils/timeSeries'
import type { TimeSeriesChannel } from '../../utils/parseLabelConfig'

interface TimeSeriesRegion {
  start: number
  end: number
  color?: string
}

interface TimeSeriesChartProps {
  data: ParsedTimeSeries
  channels?: TimeSeriesChannel[]
  regions?: TimeSeriesRegion[]
  pendingSpan?: { start: number; end: number | null } | null
  readOnly?: boolean
  /** 点击图表某处，返回对应的 X 轴值（用于 span 选择） */
  onTimeSelect?: (time: number) => void
}

/**
 * 时间序列 echarts 图表（多通道折线 + dataZoom + 区间 markArea）。
 * 点击图表通过 getZr + convertFromPixel 解析出 X 轴值。
 */
export default function TimeSeriesChart({
  data,
  channels = [],
  regions = [],
  pendingSpan = null,
  readOnly = false,
  onTimeSelect,
}: TimeSeriesChartProps) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const onSelectRef = useRef(onTimeSelect)
  onSelectRef.current = onTimeSelect

  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current)
    chartRef.current = chart

    if (!readOnly) {
      chart.getZr().on('click', (params) => {
        const x = chart.convertFromPixel({ xAxisIndex: 0 }, (params as { offsetX: number }).offsetX)
        if (onSelectRef.current && !Number.isNaN(x)) onSelectRef.current(x)
      })
    }

    const resize = () => chart.resize()
    const ro = new ResizeObserver(resize)
    ro.observe(ref.current)

    return () => {
      ro.disconnect()
      chart.dispose()
      chartRef.current = null
    }
  }, [readOnly])

  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    const configByCol = new Map(channels.map((c) => [c.column, c]))
    const series = data.channels.map((ch) => {
      const cfg = configByCol.get(ch.column)
      const seriesData = data.times.map((t, i) => [t, ch.values[i]])
      const markAreas = regions.map((r) => [
        { xAxis: r.start, itemStyle: { color: r.color ?? 'rgba(255,0,0,0.15)' } },
        { xAxis: r.end },
      ])
      const pendingArea =
        pendingSpan && pendingSpan.end != null
          ? [
              [
                { xAxis: pendingSpan.start, itemStyle: { color: 'rgba(24,144,255,0.15)' } },
                { xAxis: pendingSpan.end },
              ],
            ]
          : []
      const pendingLine =
        pendingSpan && pendingSpan.end == null
          ? [{ xAxis: pendingSpan.start, lineStyle: { color: '#1890FF', type: 'dashed' } }]
          : []
      return {
        type: 'line',
        name: cfg?.legend ?? ch.column,
        data: seriesData,
        itemStyle: cfg?.strokeColor ? { color: cfg.strokeColor } : undefined,
        showSymbol: false,
        markArea:
          markAreas.length || pendingArea.length
            ? { silent: true, data: [...markAreas, ...pendingArea] }
            : undefined,
        markLine: pendingLine.length
          ? { silent: true, symbol: 'none', data: pendingLine }
          : undefined,
      }
    })

    chart.setOption(
      {
        tooltip: { trigger: 'axis' },
        legend: { type: 'scroll', bottom: 0 },
        grid: { left: 48, right: 16, top: 16, bottom: 56 },
        xAxis: { type: 'value', scale: true },
        yAxis: { type: 'value', scale: true },
        dataZoom: [{ type: 'inside' }, { type: 'slider', height: 18, bottom: 24 }],
        series,
      },
      { notMerge: true },
    )
  }, [data, channels, regions, pendingSpan])

  return <div ref={ref} style={{ width: '100%', height: 360 }} />
}
