import { useEffect, useMemo } from 'react'
import { Empty, theme } from 'antd'
import { useEcharts } from '@/hooks/useEcharts'

const BAR_COLOR = '#1890ff'
const CHART_HEIGHT = 300

interface HyperparameterImportanceChartProps {
  importance: Record<string, number>
}

/**
 * 超参重要性 (fANOVA): 各超参对目标指标的影响度横向 bar, 按值降序.
 * 完成 trial 不足时展示空态.
 */
export default function HyperparameterImportanceChart({
  importance,
}: HyperparameterImportanceChartProps) {
  const { token } = theme.useToken()
  const { ref, chartRef } = useEcharts()

  const entries = useMemo(
    () => Object.entries(importance).sort((a, b) => b[1] - a[1]),
    [importance],
  )

  const option = useMemo(() => {
    if (entries.length === 0) return null
    const axisColor = token.colorTextSecondary
    const splitColor = token.colorSplit

    return {
      backgroundColor: 'transparent',
      tooltip: {
        trigger: 'item',
        backgroundColor: token.colorBgElevated,
        borderColor: token.colorBorderSecondary,
        textStyle: { color: token.colorText, fontSize: 12 },
        formatter: (params: unknown) => {
          const item = params as { name: string; value: number; marker: string }
          return `${item.marker} ${item.name}：<b>${item.value.toFixed(4)}</b>`
        },
      },
      grid: { left: 8, right: 40, top: 12, bottom: 8, containLabel: true },
      xAxis: {
        type: 'value',
        axisLabel: { color: axisColor },
        axisLine: { show: false },
        splitLine: { lineStyle: { color: splitColor } },
      },
      yAxis: {
        type: 'category',
        data: entries.map(([name]) => name),
        inverse: true,
        axisLabel: { color: token.colorText },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      series: [
        {
          type: 'bar',
          data: entries.map(([name, val]) => ({ name, value: val })),
          color: BAR_COLOR,
          barWidth: 14,
          itemStyle: { borderRadius: [0, 4, 4, 0] },
        },
      ],
    }
  }, [entries, token])

  useEffect(() => {
    if (option && chartRef.current) chartRef.current.setOption(option, { notMerge: true })
  }, [option, chartRef])

  if (entries.length === 0) {
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
          description="完成 trial 不足，暂无法计算超参重要性"
        />
      </div>
    )
  }

  return <div ref={ref} style={{ width: '100%', height: CHART_HEIGHT }} />
}
