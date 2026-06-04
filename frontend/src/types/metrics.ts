export interface GpuMetricPoint {
  gpuIndex: number
  utilizationPercent: number
  memoryUsedMib: number
  memoryTotalMib: number
  temperatureC: number
  powerW: number
}

export interface TimeSeriesPoint {
  timestamp: string
  value: number
  label: string
}

export interface GpuMetricsData {
  gpuMetrics: GpuMetricPoint[]
  gpuUtilizationHistory: TimeSeriesPoint[]
  metricsUrl: string | null
  prometheusAvailable: boolean
  timestamp: string
}

/** Return the average GPU utilization across all GPUs, or 0 if no data. */
export function aggregateGpuUtilization(metrics: GpuMetricPoint[]): number {
  if (!metrics.length) return 0
  return metrics.reduce((sum, m) => sum + m.utilizationPercent, 0) / metrics.length
}

/** Return the total memory usage across all GPUs (MiB). */
export function aggregateMemoryUsage(metrics: GpuMetricPoint[]): { used: number; total: number } {
  const used = metrics.reduce((sum, m) => sum + m.memoryUsedMib, 0)
  const total = metrics.reduce((sum, m) => sum + m.memoryTotalMib, 0)
  return { used, total }
}

/** Return the maximum temperature across all GPUs, or 0 if no data. */
export function maxGpuTemperature(metrics: GpuMetricPoint[]): number {
  if (!metrics.length) return 0
  return Math.max(...metrics.map((m) => m.temperatureC))
}

/** Return the total power consumption across all GPUs (W). */
export function totalGpuPower(metrics: GpuMetricPoint[]): number {
  return metrics.reduce((sum, m) => sum + m.powerW, 0)
}
