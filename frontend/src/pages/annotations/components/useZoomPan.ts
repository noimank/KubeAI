import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type Konva from 'konva'
import { appendAuthToken } from '@/utils/constants'

export interface Point {
  x: number
  y: number
}

export interface ZoomPanController {
  image: HTMLImageElement | null
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
  pointerToImage: () => Point | null
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
 * 收拢标注画布的缩放/平移逻辑。形状坐标统一存储为「图像自然像素坐标」,
 * 渲染时由 Stage 自身 scaleX/Y + x/y 映射到屏幕。
 *
 * 仅图像首次加载时自动 fitToWindow；容器 resize 后不会自动重新 fit，
 * 避免因 region list 出现/消失等布局变动触发 fit → 尺寸变动 → fit 的无尽循环。
 */
export function useZoomPan(imageUrl: string | undefined): ZoomPanController {
  const containerRef = useRef<HTMLDivElement>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const stageScaleRef = useRef(1)
  const stagePosRef = useRef<Point>({ x: 0, y: 0 })
  const spaceDownRef = useRef(false)
  const didInitialFitRef = useRef(false)

  const [image, setImage] = useState<HTMLImageElement | null>(null)
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

  // ── 图片加载 ───────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!imageUrl) {
      setImage(null)
      didInitialFitRef.current = false
      return
    }
    let cancelled = false
    didInitialFitRef.current = false
    const img = new window.Image()
    img.crossOrigin = 'anonymous'
    img.src = appendAuthToken(imageUrl)
    img.onload = () => {
      if (!cancelled) setImage(img)
    }
    img.onerror = () => {
      if (!cancelled) setImage(null)
    }
    return () => {
      cancelled = true
    }
  }, [imageUrl])

  // ── 容器尺寸追踪 ───────────────────────────────────────────────────────────

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setStageSize({
          width: entry.contentRect.width,
          height: Math.max(400, entry.contentRect.height),
        })
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // ── fitToWindow：仅在图片首次加载时自动执行，后续由用户手动触发 ──────────

  const fitToWindow = useCallback(() => {
    if (!image) return
    const scale = Math.min(stageSize.width / image.width, stageSize.height / image.height)
    setStageScale(scale)
    setStagePos({
      x: (stageSize.width - image.width * scale) / 2,
      y: (stageSize.height - image.height * scale) / 2,
    })
  }, [image, stageSize.width, stageSize.height, setStageScale, setStagePos])

  // 图片加载后首次适应窗口
  useEffect(() => {
    if (!image || didInitialFitRef.current) return
    didInitialFitRef.current = true
    fitToWindow()
    // 仅依赖 image 可用性；resize 由用户手动触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [image])

  const resetZoom = useCallback(() => {
    if (!image) return
    // 100% (1:1 图像像素),居中
    setStageScale(1)
    setStagePos({
      x: (stageSize.width - image.width) / 2,
      y: (stageSize.height - image.height) / 2,
    })
  }, [image, stageSize.width, stageSize.height, setStageScale, setStagePos])

  const applyZoom = useCallback(
    (newScaleRaw: number, anchor: Point) => {
      const oldScale = stageScaleRef.current
      const newScale = clampScale(newScaleRaw)
      if (newScale === oldScale) return
      const pos = stagePosRef.current
      const imgX = (anchor.x - pos.x) / oldScale
      const imgY = (anchor.y - pos.y) / oldScale
      setStageScale(newScale)
      setStagePos({
        x: anchor.x - imgX * newScale,
        y: anchor.y - imgY * newScale,
      })
    },
    [setStageScale, setStagePos],
  )

  const zoomBy = useCallback(
    (factor: number) => {
      applyZoom(stageScaleRef.current * factor, {
        x: stageSize.width / 2,
        y: stageSize.height / 2,
      })
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
      // 触控板缩放时 ctrlKey 为 true,方向相反
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

  const pointerToImage = useCallback((): Point | null => {
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
      image,
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
      pointerToImage,
      visibleStrokeWidth,
      visibleAnchorSize,
      onWheel,
      onStageDragEnd,
    }),
    [
      image,
      stageSize,
      stageScale,
      stagePos,
      panMode,
      panEffective,
      fitToWindow,
      resetZoom,
      zoomBy,
      pointerToImage,
      visibleStrokeWidth,
      visibleAnchorSize,
      onWheel,
      onStageDragEnd,
    ],
  )
}
