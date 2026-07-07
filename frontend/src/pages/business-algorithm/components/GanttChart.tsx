import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'

interface Operation {
  id: number
  device: string
  startTime: number
  endTime: number
  duration: number
}

interface SolutionInfo {
  jobId: number
  operations: Operation[]
}

interface DeviceUtilization {
  device: string
  totalTime: number
  utilizationRate: number
}

interface Props {
  solutionInfo: SolutionInfo[]
  deviceUtilization: DeviceUtilization[]
}

const COLORS = ['#1677FF', '#52C41A', '#FAAD14', '#FF4D4F', '#722ED1', '#EB2F96']

export default function GanttChart({ solutionInfo, deviceUtilization }: Props) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstance = useRef<echarts.ECharts | null>(null)

  useEffect(() => {
    if (!chartRef.current || !solutionInfo?.length) return

    if (chartInstance.current) {
      chartInstance.current.dispose()
    }

    const chart = echarts.init(chartRef.current)
    chartInstance.current = chart

    let maxTime = 0
    solutionInfo.forEach((task) => {
      ;(task.operations || []).forEach((op) => {
        if (op.endTime > maxTime) maxTime = op.endTime
      })
    })
    maxTime = Math.ceil(maxTime * 1.1)

    const deviceNames = (deviceUtilization || []).map((d) => d.device)

    const series = solutionInfo.map((task, taskIndex) => {
      const data = (task.operations || []).map((op) => ({
        value: [op.startTime, op.endTime, op.device],
        itemStyle: { color: COLORS[taskIndex % COLORS.length] },
        _job: `作业${task.jobId}`,
        _startTime: op.startTime,
        _endTime: op.endTime,
        _duration: op.duration,
      }))
      return {
        name: `作业${task.jobId}`,
        type: 'custom',
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        renderItem: (params: any, api: any) => {
          const categoryIndex = api.value(2)
          const start = api.coord([api.value(0), categoryIndex])
          const end = api.coord([api.value(1), categoryIndex])
          const height = api.size([0, 1])[1] * 0.6

          const rectShape = echarts.graphic.clipRectByRect(
            {
              x: start[0],
              y: start[1] - height / 2,
              width: end[0] - start[0],
              height: height,
            },
            {
              x: params.coordSys.x,
              y: params.coordSys.y,
              width: params.coordSys.width,
              height: params.coordSys.height,
            },
          )
          return (
            rectShape && {
              type: 'rect',
              transition: ['shape'],
              shape: rectShape,
              style: api.style(),
            }
          )
        },
        data,
        encode: { x: [0, 1], y: 2 },
        tooltip: {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          formatter: (params: any) => {
            const d = params.data
            return `${d._job}<br/>开始: ${d._startTime}<br/>结束: ${d._endTime}<br/>持续: ${d._duration}`
          },
        },
      }
    })

    chart.setOption({
      tooltip: { trigger: 'item' },
      grid: { left: 100, right: 30, top: 20, bottom: 40 },
      xAxis: {
        type: 'value',
        min: 0,
        max: maxTime,
        name: '时间',
        splitLine: { show: true, lineStyle: { color: 'rgba(0,0,0,0.1)' } },
      },
      yAxis: {
        type: 'category',
        data: deviceNames,
        name: '工序',
        splitLine: { show: false },
      },
      series,
    })

    const handleResize = () => chart.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.dispose()
      chartInstance.current = null
    }
  }, [solutionInfo, deviceUtilization])

  return (
    <div
      ref={chartRef}
      style={{
        width: '100%',
        height: 400,
        border: '1px solid var(--ant-color-border)',
        borderRadius: 4,
      }}
    />
  )
}
