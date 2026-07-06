import { useMemo } from 'react'
import type { GpuMetricPoint, TimeSeriesPoint } from '@/types/metrics'

const LOW_GPU_THRESHOLD = 10
const HIGH_TEMP_THRESHOLD = 80
const MIN_RECENT_SAMPLES = 10

interface UseGpuAlertsOptions {
  /** Threshold for low GPU utilization warning (percent). */
  lowUtilThreshold?: number
  /** Lookback window for low utilization check (ms). */
  warningWindowMs?: number
  /** Minimum recent samples required before triggering warning. */
  minRecentSamples?: number
  /** Threshold for high GPU temperature warning (Celsius). */
  highTempThreshold?: number
}

interface UseGpuAlertsResult {
  shouldWarnGpu: boolean
  shouldWarnTemp: boolean
}

export function useGpuAlerts(
  gpuMetrics: GpuMetricPoint[],
  gpuUtilizationHistory: TimeSeriesPoint[],
  opts: UseGpuAlertsOptions = {},
): UseGpuAlertsResult {
  const {
    lowUtilThreshold = LOW_GPU_THRESHOLD,
    warningWindowMs: windowMs,
    minRecentSamples = MIN_RECENT_SAMPLES,
    highTempThreshold = HIGH_TEMP_THRESHOLD,
  } = opts

  const shouldWarnGpu = useMemo(() => {
    if (!gpuUtilizationHistory.length) return false
    const cutoff = Date.now() - (windowMs ?? 5 * 60 * 1000)
    const recent = gpuUtilizationHistory.filter((p) => new Date(p.timestamp).getTime() >= cutoff)
    if (recent.length < minRecentSamples) return false
    return recent.every((p) => p.value < lowUtilThreshold)
  }, [gpuUtilizationHistory, lowUtilThreshold, windowMs, minRecentSamples])

  const shouldWarnTemp = useMemo(() => {
    return gpuMetrics.some((m) => m.temperatureC >= highTempThreshold)
  }, [gpuMetrics, highTempThreshold])

  return { shouldWarnGpu, shouldWarnTemp }
}
