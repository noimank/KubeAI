import { useEffect, useMemo } from 'react'
import { Empty, theme } from 'antd'
import { useEcharts } from '@/hooks/useEcharts'
import type { TuningDirection, TuningTrialPoint } from '@/types/tuning'

const VALUE_COLOR = '#1890ff'
const BEST_COLOR = '#08979c'
const CHART_HEIGHT = 300

interface OptimizationHistoryChartProps {
  history: TuningTrialPoint[]
  direction: TuningDirection
}

/**
 * 优化历史: 每个已完成 trial 的目标值散点折线 + 最优值(累计) 包络线,
 * 最优 trial 以实心点高亮. 无完成 trial 时展示空态.
 */
export default function OptimizationHistoryChart({
  history,
  direction,
}: OptimizationHistoryChartProps) {
  const { token } = theme.useToken()
  const { ref, chartRef } = useEcharts()

  const valued = useMemo(
    () =>
      history
        .filter((t) => t.value !== undefined && t.value !== null)
        .sort((a, b) => a.trialNumber - b.trialNumber),
    [history],
  )

  const bestSoFar = useMemo(() => {
    let best: number | null = null
    return valued.map((t) => {
      const v = t.value as number
      best = best === null ? v : direction === 'minimize' ? Math.min(best, v) : Math.max(best, v)
      return best
    })
  }, [valued, direction])

  const option = useMemo(() => {
    if (valued.length === 0) return null
    const pointData = valued.map((t) => [t.trialNumber, t.value])
    const bestData = valued.map((t, i) => [t.trialNumber, bestSoFar[i]])
    const bestValue = bestSoFar[bestSoFar.length - 1]
    const bestTrial = valued[valued.length - 1]
    const axisColor = token.colorTextSecondary
    const splitColor = token.colorSplit

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'axis',
        backgroundColor: token.colorBgElevated,
        borderColor: token.colorBorderSecondary,
        textStyle: { color: token.colorText, fontSize: 12 },
        formatter: (params: unknown) => {
          const arr = params as Array<{ seriesName: string; data: number[]; marker: string }>
          const trial = valued.find((t) => t.trialNumber === arr[0]?.data[0])
          const lines = arr.map((p) => `${p.marker} ${p.seriesName}：<b>${p.data[1]}</b>`)
          if (trial?.params && Object.keys(trial.params).length > 0) {
            const paramsText = Object.entries(trial.params)
              .map(([k, v]) => `${k}=${String(v)}`)
              .join('，')
            lines.push(`<span style="color:${token.colorTextSecondary}">参数：${paramsText}</span>`)
          }
          return lines.join('<br/>')
        },
      },
      legend: { bottom: 0, textStyle: { color: token.colorText } },
      grid: { left: 52, right: 24, top: 24, bottom: 56 },
      xAxis: {
        type: 'value',
        name: 'Trial',
        nameTextStyle: { color: axisColor },
        minInterval: 1,
        axisLabel: { color: axisColor },
        axisLine: { lineStyle: { color: splitColor } },
        splitLine: { show: false },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: axisColor },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: splitColor } },
      },
      series: [
        {
          name: '目标值',
          type: 'line',
          data: pointData,
          color: VALUE_COLOR,
          symbol: 'circle',
          symbolSize: 7,
          connectNulls: false,
          lineStyle: { width: 2 },
        },
        {
          name: '最优值(累计)',
          type: 'line',
          data: bestData,
          color: BEST_COLOR,
          symbol: 'none',
          lineStyle: { width: 2, type: 'dashed' },
          markPoint: {
            symbol: 'circle',
            symbolSize: 10,
            itemStyle: { color: BEST_COLOR, borderColor: '#fff', borderWidth: 2 },
            data: [{ coord: [bestTrial.trialNumber, bestValue] }],
          },
        },
      ],
    }
  }, [valued, bestSoFar, token])

  useEffect(() => {
    if (option && chartRef.current) chartRef.current.setOption(option, { notMerge: true })
  }, [option, chartRef])

  if (valued.length === 0) {
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
          description="暂无已完成的 trial，完成后将展示优化历史"
        />
      </div>
    )
  }

  return <div ref={ref} style={{ width: '100%', height: CHART_HEIGHT }} />
}
