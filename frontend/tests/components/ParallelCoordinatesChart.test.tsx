import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import ParallelCoordinatesChart from '@/pages/tuning/components/ParallelCoordinatesChart'
import type { TuningTrialPoint } from '@/types/tuning'

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

// echarts.init 返回固定 mock 实例, 以便从 setOption 捕获构造的 option.
const mocks = vi.hoisted(() => {
  const setOption = vi.fn()
  return {
    setOption,
    chart: { setOption, resize: vi.fn(), dispose: vi.fn() },
  }
})
vi.mock('echarts', () => ({ init: () => mocks.chart }))

const history: TuningTrialPoint[] = [
  { trialNumber: 0, value: 0.9, params: { HP_EPOCHS: 36 }, state: 'complete' },
  { trialNumber: 1, value: 0.8, params: { HP_EPOCHS: 32 }, state: 'complete' },
]

describe('ParallelCoordinatesChart', () => {
  beforeEach(() => mocks.setOption.mockClear())

  it('为目标指标绘制末轴, 其 dim 与 visualMap 着色维度一致 (避免线条退化空白)', () => {
    render(<ParallelCoordinatesChart history={history} metricName="accuracy" />)
    expect(mocks.setOption).toHaveBeenCalled()
    const option = mocks.setOption.mock.calls[0][0]
    const axes = option.parallelAxis as Array<{ dim: number; type: string; name: string }>
    const valueAxis = axes[axes.length - 1]
    // 末轴 = 目标值轴, 必须存在且与着色维度 (visualMap.dimension) 对齐, 否则该维无轴承载 → 图空白.
    expect(valueAxis.dim).toBe(option.visualMap.dimension)
    expect(valueAxis.type).toBe('value')
    expect(valueAxis.name).toBe('accuracy')
  })

  it('完成 trial <2 时展示空态且不渲染图表', () => {
    render(<ParallelCoordinatesChart history={[history[0]]} />)
    expect(screen.getByText('完成 trial 不足，暂无法绘制平行坐标')).toBeDefined()
    expect(mocks.setOption).not.toHaveBeenCalled()
  })
})
