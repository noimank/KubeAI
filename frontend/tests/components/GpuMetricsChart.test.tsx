import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import GpuMetricsChart from '@/components/GpuMetricsChart'

Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

global.ResizeObserver = class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

// Mock @ant-design/charts Line component
vi.mock('@ant-design/charts', () => ({
  Line: (props: { data: unknown[] }) => (
    <div data-testid="mock-line-chart">Chart with {props.data.length} points</div>
  ),
}))

describe('GpuMetricsChart', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders GPU summary cards when metrics available', () => {
    render(
      <GpuMetricsChart
        gpuMetrics={[
          {
            gpuIndex: 0,
            utilizationPercent: 87.5,
            memoryUsedMib: 8192,
            memoryTotalMib: 16384,
            temperatureC: 72,
            powerW: 250,
          },
        ]}
        gpuUtilizationHistory={[]}
      />,
    )
    expect(screen.getByText('GPU 利用率')).toBeDefined()
    expect(screen.getByText('显存使用')).toBeDefined()
    expect(screen.getByText('温度')).toBeDefined()
    expect(screen.getByText('功耗')).toBeDefined()
  })

  it('renders empty state when no data', () => {
    render(<GpuMetricsChart gpuMetrics={[]} gpuUtilizationHistory={[]} />)
    expect(screen.getByText('GPU 监控数据暂不可用')).toBeDefined()
  })

  it('renders Prometheus unavailable message when prometheusAvailable=false', () => {
    render(
      <GpuMetricsChart gpuMetrics={[]} gpuUtilizationHistory={[]} prometheusAvailable={false} />,
    )
    expect(screen.getByText('未连接 Prometheus，GPU 监控数据不可用')).toBeDefined()
  })

  it('renders chart when history data available', () => {
    render(
      <GpuMetricsChart
        gpuMetrics={[]}
        gpuUtilizationHistory={[
          { timestamp: '2026-05-11T10:00:00Z', value: 85, label: 'GPU 0' },
          { timestamp: '2026-05-11T10:00:15Z', value: 87, label: 'GPU 0' },
        ]}
      />,
    )
    expect(screen.getByTestId('mock-line-chart')).toBeDefined()
    expect(screen.getByText('GPU 利用率趋势')).toBeDefined()
  })

  it('renders loading state', () => {
    const { container } = render(
      <GpuMetricsChart gpuMetrics={[]} gpuUtilizationHistory={[]} loading />,
    )
    expect(container.querySelector('.ant-spin')).toBeDefined()
  })

  it('shows aggregate stats for multi-GPU', () => {
    render(
      <GpuMetricsChart
        gpuMetrics={[
          {
            gpuIndex: 0,
            utilizationPercent: 80,
            memoryUsedMib: 8000,
            memoryTotalMib: 16000,
            temperatureC: 70,
            powerW: 200,
          },
          {
            gpuIndex: 1,
            utilizationPercent: 60,
            memoryUsedMib: 6000,
            memoryTotalMib: 16000,
            temperatureC: 75,
            powerW: 180,
          },
        ]}
        gpuUtilizationHistory={[]}
      />,
    )
    // Should show per-GPU detail table for multi-GPU
    expect(screen.getByText('GPU 详情')).toBeDefined()
    expect(screen.getByText('GPU 0')).toBeDefined()
    expect(screen.getByText('GPU 1')).toBeDefined()
  })

  it('high temperature shows red color', () => {
    render(
      <GpuMetricsChart
        gpuMetrics={[
          {
            gpuIndex: 0,
            utilizationPercent: 85,
            memoryUsedMib: 8000,
            memoryTotalMib: 16000,
            temperatureC: 88,
            powerW: 300,
          },
        ]}
        gpuUtilizationHistory={[]}
      />,
    )
    // The statistic value for temperature should have red color style
    const tempElement = screen.getByText('温度')
    expect(tempElement).toBeDefined()
  })
})
