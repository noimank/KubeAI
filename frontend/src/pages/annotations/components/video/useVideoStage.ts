import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type Konva from 'konva'

export interface Point {
  x: number
  y: number
}

export interface VideoStageController {
  stageSize: { width: number; height: number }
  stageScale: number
  stagePos: Point
  panMode: boolean
  setPanMode: (value: boolean) => void
  panEffective: boolean
  containerRef: React.RefObject<HTMLDivElement>
  stageRef: React.RefObject<Konva.Stage>
  fitToWindow: () => void
  resetZoom: () => void
  zoomBy: (factor: number) => void
  pointerToNatural: () => Point | null
  visibleStrokeWidth: (base?: number) => number
  visibleAnchorSize: (base?: number) => number
  onWheel: (e: Konva.KonvaEventObject<WheelEvent>) => void
  onStageDragEnd: (e: Konva.KonvaEventObject<DragEvent>) => void
}

const MIN_SCALE = 0.1
const MAX_SCALE = 20
const SCALE_BY = 1.08

function clampScale(value: number): number {
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, value))
}

/**
 * 视频画布的缩放/平移变换 —— Stage 在「视频自然像素空间」运行
 *（scaleX/Y 把视频像素映射到屏幕），形状坐标统一存百分比，边界处转换。
 *
 * 与 useZoomPan 的变换数学同源，但不加载媒体（尺寸由 video 元数据提供）。
 */
export function useVideoStage(naturalWidth: number, naturalHeight: number): VideoStageController {
  const containerRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const stageScaleRef = useRef(1)
  const stagePosRef = useRef<Point>({ x: 0, y: 0 })
  const spaceDownRef = useRef(false)
  const didInitialFitRef = useRef(false)

  const [stageSize, setStageSize] = useState({ width: 600, height: 400 })
  const [stageScale, setStageScaleState] = useState(1)
  const [stagePos, setStagePosState] = useState<Point>({ x: 0, y: 0 })
  const [panMode, setPanMode] = useState(false)
  const [spacePressed, setSpacePressed] = useState(false)

  const setStageScale = useCallback((value: number) => {
    stageScaleRef.current = value
    setStageScaleState(value)
  }, [])
  const setStagePos = useCallback((value: Point) => {
    stagePosRef.current = value
    setStagePosState(value)
  }, [])

  // 容器尺寸追踪
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setStageSize({
          width: entry.contentRect.width,
          height: Math.max(300, entry.contentRect.height),
        })
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const fitToWindow = useCallback(() => {
    if (!naturalWidth || !naturalHeight) return
    const container = containerRef.current
    if (!container) return
    const w = container.clientWidth
    const h = Math.max(300, container.clientHeight)
    const scale = Math.min(w / naturalWidth, h / naturalHeight)
    setStageScale(scale)
    setStagePos({ x: (w - naturalWidth * scale) / 2, y: (h - naturalHeight * scale) / 2 })
  }, [naturalWidth, naturalHeight, setStageScale, setStagePos])

  // 容器尺寸就绪 + 视频自然尺寸已知时首次适应窗口
  useEffect(() => {
    if (!naturalWidth || !naturalHeight) return
    if (stageSize.width <= 0 || stageSize.height <= 0) return
    if (didInitialFitRef.current) return
    didInitialFitRef.current = true
    fitToWindow()
  }, [naturalWidth, naturalHeight, stageSize, fitToWindow])

  const resetZoom = useCallback(() => {
    if (!naturalWidth || !naturalHeight) return
    setStageScale(1)
    setStagePos({
      x: (stageSize.width - naturalWidth) / 2,
      y: (stageSize.height - naturalHeight) / 2,
    })
  }, [naturalWidth, naturalHeight, stageSize.width, stageSize.height, setStageScale, setStagePos])

  const applyZoom = useCallback(
    (newScaleRaw: number, anchor: Point) => {
      const oldScale = stageScaleRef.current
      const newScale = clampScale(newScaleRaw)
      if (newScale === oldScale) return
      const pos = stagePosRef.current
      const imgX = (anchor.x - pos.x) / oldScale
      const imgY = (anchor.y - pos.y) / oldScale
      setStageScale(newScale)
      setStagePos({ x: anchor.x - imgX * newScale, y: anchor.y - imgY * newScale })
    },
    [setStageScale, setStagePos],
  )

  const zoomBy = useCallback(
    (factor: number) => {
      applyZoom(stageScaleRef.current * factor, { x: stageSize.width / 2, y: stageSize.height / 2 })
    },
    [applyZoom, stageSize.width, stageSize.height],
  )

  const onWheel = useCallback(
    (e: Konva.KonvaEventObject<WheelEvent>) => {
      e.evt.preventDefault()
      const stage = stageRef.current
      if (!stage) return
      const pointer = stage.getPointerPosition()
      if (!pointer) return
      let direction = e.evt.deltaY > 0 ? -1 : 1
      if (e.evt.ctrlKey) direction = -direction
      const factor = direction > 0 ? SCALE_BY : 1 / SCALE_BY
      applyZoom(stageScaleRef.current * factor, pointer)
    },
    [applyZoom],
  )

  const onStageDragEnd = useCallback(
    (e: Konva.KonvaEventObject<DragEvent>) => {
      const target = e.target
      if (target !== e.target.getStage()) return
      setStagePos({ x: target.x(), y: target.y() })
    },
    [setStagePos],
  )

  const pointerToNatural = useCallback((): Point | null => {
    const stage = stageRef.current
    if (!stage) return null
    const pointer = stage.getPointerPosition()
    if (!pointer) return null
    const pos = stagePosRef.current
    const scale = stageScaleRef.current
    return { x: (pointer.x - pos.x) / scale, y: (pointer.y - pos.y) / scale }
  }, [])

  const visibleStrokeWidth = useCallback(
    (base = 2) => Math.max(0.5, base / stageScale),
    [stageScale],
  )
  const visibleAnchorSize = useCallback((base = 10) => Math.max(4, base / stageScale), [stageScale])

  useEffect(() => {
    const isEditable = (target: EventTarget | null) => {
      const tag = (target as HTMLElement | null)?.tagName
      return tag === 'INPUT' || tag === 'TEXTAREA'
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.code !== 'Space' || e.repeat || isEditable(e.target)) return
      e.preventDefault()
      spaceDownRef.current = true
      setSpacePressed(true)
    }
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.code !== 'Space') return
      spaceDownRef.current = false
      setSpacePressed(false)
    }
    window.addEventListener('keydown', onKeyDown)
    window.addEventListener('keyup', onKeyUp)
    return () => {
      window.removeEventListener('keydown', onKeyDown)
      window.removeEventListener('keyup', onKeyUp)
    }
  }, [])

  const panEffective = panMode || spacePressed

  return useMemo(
    () => ({
      stageSize,
      stageScale,
      stagePos,
      panMode,
      setPanMode,
      panEffective,
      containerRef,
      stageRef,
      fitToWindow,
      resetZoom,
      zoomBy,
      pointerToNatural,
      visibleStrokeWidth,
      visibleAnchorSize,
      onWheel,
      onStageDragEnd,
    }),
    [
      stageSize,
      stageScale,
      stagePos,
      panMode,
      panEffective,
      fitToWindow,
      resetZoom,
      zoomBy,
      pointerToNatural,
      visibleStrokeWidth,
      visibleAnchorSize,
      onWheel,
      onStageDragEnd,
    ],
  )
}
