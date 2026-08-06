import { useCallback, useRef } from 'react'
import * as echarts from 'echarts'

/**
 * echarts 图表的统一生命周期: 回调 ref 在容器挂载时 init → ResizeObserver 自适应 → 卸载/重挂时 dispose.
 * 组件通过 chartRef.current.setOption(option, { notMerge: true }) 渲染.
 *
 * 用回调 ref 而非 useEffect(..., []): 图表容器在空态时是条件渲染的 (valued.length===0 走 <Empty> 分支,
 * 不渲染 <div ref>). 若用空依赖 effect, 首次空态挂载时 ref.current 为 null, effect 提前 return,
 * 此后数据到达容器才挂载, 但 effect 不会重跑 → chartRef 永远为 null → 图表永不渲染.
 * 回调 ref 保证 init 一定在 DOM 节点实际挂载后触发, 且重挂/卸载时正确 dispose 上一份实例.
 */
export function useEcharts() {
  const chartRef = useRef<echarts.ECharts | null>(null)
  const resizeObserverRef = useRef<ResizeObserver | null>(null)

  const ref = useCallback((node: HTMLDivElement | null) => {
    // 先释放上一份实例 (重挂 / 卸载场景), 避免泄漏
    if (chartRef.current) {
      resizeObserverRef.current?.disconnect()
      chartRef.current.dispose()
      chartRef.current = null
      resizeObserverRef.current = null
    }
    if (node) {
      const chart = echarts.init(node)
      const ro = new ResizeObserver(() => chart.resize())
      ro.observe(node)
      chartRef.current = chart
      resizeObserverRef.current = ro
    }
  }, [])

  return { ref, chartRef }
}
