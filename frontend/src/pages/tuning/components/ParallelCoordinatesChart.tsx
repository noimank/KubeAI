import { useEffect, useMemo } from 'react'
import { Empty, theme } from 'antd'
import { useEcharts } from '@/hooks/useEcharts'
import type { TuningTrialPoint } from '@/types/tuning'

const CHART_HEIGHT = 300
const MAX_DIMS = 8
// 顺序色带 (antd blue-4 → blue-9), 按目标值单调明暗着色
const RAMP_LIGHT = '#69b1ff'
const RAMP_DARK = '#003eb3'

interface ParallelCoordinatesChartProps {
  history: TuningTrialPoint[]
  /** 用于维度排序: 重要性高的参数排前, 无值时按出现顺序. */
  importance?: Record<string, number>
}

/** 数值轴 min==max 时扩张区间, 避免 echarts 退化布局. */
function expandRange(min: number, max: number): [number, number] {
  if (min !== max) return [min, max]
  return min === 0 ? [-1, 1] : [min * 0.9, max * 1.1]
}

/**
 * 平行坐标: 每个已完成 trial 一条线, 各超参为一条平行轴, 按目标值连续着色.
 * 完成 trial <2 时展示空态.
 */
export default function ParallelCoordinatesChart({
  history,
  importance,
}: ParallelCoordinatesChartProps) {
  const { token } = theme.useToken()
  const { ref, chartRef } = useEcharts()

  const rows = useMemo(
    () =>
      history
        .filter((t) => t.value !== undefined && t.value !== null)
        .sort((a, b) => a.trialNumber - b.trialNumber),
    [history],
  )

  const { dims, data, min, max } = useMemo(() => {
    if (rows.length < 2) return { dims: [], data: [], min: 0, max: 0 }

    const present = new Set<string>()
    rows.forEach((t) => Object.keys(t.params).forEach((k) => present.add(k)))
    let dims = Array.from(present)
    if (importance && Object.keys(importance).length > 0) {
      dims.sort((a, b) => (importance[b] ?? 0) - (importance[a] ?? 0))
    }
    dims = dims.slice(0, MAX_DIMS)

    const values = rows.map((t) => t.value as number)
    const [min, max] = expandRange(Math.min(...values), Math.max(...values))

    const data = rows.map((t) => [...dims.map((d) => t.params[d]), t.value as number])
    return { dims, data, min, max }
  }, [rows, importance])

  const option = useMemo(() => {
    if (dims.length === 0) return null
    const axisColor = token.colorTextSecondary

    const parallelAxis = dims.map((d, i) => {
      const col = data.map((row) => row[i])
      if (col.every((v) => typeof v === 'number')) {
        const nums = col as number[]
        const [min, max] = expandRange(Math.min(...nums), Math.max(...nums))
        return {
          dim: i,
          name: d,
          type: 'value',
          min,
          max,
          nameTextStyle: { color: token.colorText },
        }
      }
      return {
        dim: i,
        name: d,
        type: 'category',
        categoryData: Array.from(new Set(col.map(String))),
        nameTextStyle: { color: token.colorText },
      }
    })

    return {
      backgroundColor: 'transparent',
      parallel: {
        left: 48,
        right: 64,
        top: 24,
        bottom: 44,
        parallelAxisDefault: {
          axisLabel: { color: axisColor },
          axisLine: { lineStyle: { color: token.colorSplit } },
        },
      },
      parallelAxis,
      tooltip: {
        backgroundColor: token.colorBgElevated,
        borderColor: token.colorBorderSecondary,
        textStyle: { color: token.colorText, fontSize: 12 },
      },
      visualMap: {
        type: 'continuous',
        parallelIndex: 0,
        dimension: dims.length,
        min,
        max,
        inRange: { color: [RAMP_LIGHT, RAMP_DARK] },
        orient: 'horizontal',
        bottom: 0,
        left: 'center',
        itemHeight: 120,
        itemWidth: 10,
        textStyle: { color: axisColor },
      },
      series: [{ type: 'parallel', lineStyle: { width: 1.5 }, data }],
    }
  }, [dims, data, min, max, token])

  useEffect(() => {
    if (option && chartRef.current) chartRef.current.setOption(option, { notMerge: true })
  }, [option, chartRef])

  if (dims.length === 0) {
    return (
      <div
        style={{
          height: CHART_HEIGHT,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description="完成 trial 不足，暂无法绘制平行坐标"
        />
      </div>
    )
  }

  return <div ref={ref} style={{ width: '100%', height: CHART_HEIGHT }} />
}
