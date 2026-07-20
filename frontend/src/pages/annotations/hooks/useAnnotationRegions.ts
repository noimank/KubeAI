import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { AnnotationResultItem } from '@/types/annotation'

// ── Region value (判别联合) ───────────────────────────────────────────────────
// 几何/区间负载按 kind 判别；hook 本身与 kind 无关，多态只在边缘处理
// (各 annotator 的窄化过滤、serializer、validator)。

export interface RectangleValue {
  kind: 'rectangle'
  x: number
  y: number
  width: number
  height: number
  rotation: number
}
export interface PolygonValue {
  kind: 'polygon'
  /** 顶点，图像像素坐标 [[x1,y1], ...] */
  points: [number, number][]
}
export interface KeyPointValue {
  kind: 'keypoint'
  x: number
  y: number
  width: number
}
export interface EllipseValue {
  kind: 'ellipse'
  /** 包围盒左上角 X（与 Rectangle 同坐标系，serializer 转为中心 radiusX/Y） */
  x: number
  y: number
  width: number
  height: number
  rotation: number
}
export interface BrushValue {
  kind: 'brush'
  /** LabelStudio RLE 编码的掩码字符串 */
  rle: string
  originalWidth: number
  originalHeight: number
}
export interface TextSpanValue {
  kind: 'textspan'
  /** 字符偏移起止 + 选中文本（Labels / HyperTextLabels 控件） */
  start: number
  end: number
  text: string
}

/** ParagraphLabels：单条对话 utterance 内的文本 span */
export interface ParagraphSpanValue {
  kind: 'paragraphspan'
  /** 所属 utterance 的标识（数组下标字符串） */
  paragraphId: string
  start: number
  end: number
  text: string
}

/** Chat：消息即区域 —— 点击一条消息选中它，perRegion 控件挂载其上（RLHF） */
export interface MessageValue {
  kind: 'message'
  /** 消息标识（数组下标字符串） */
  messageId: string
  /** 消息角色（user/assistant…），供 whenRole 条件使用 */
  role?: string
}

/** TimeSeriesLabels：时间序列上的区间（异常/事件） */
export interface TimeSeriesSpanValue {
  kind: 'timeseries'
  start: number
  end: number
  instant: boolean
}

/** Audio Labels：音频波形上的区间（声音事件检测）—— start/end 为秒 */
export interface AudioSpanValue {
  kind: 'audio'
  start: number
  end: number
}

/** VideoRectangle 关键帧：坐标百分比 0-100（LS 规范），frame 1-based。
 *  enabled 控制 lifespan（false = 从该帧起隐藏，直到下一个 enabled=true）。 */
export interface VideoKeyframe {
  frame: number
  enabled: boolean
  x: number
  y: number
  width: number
  height: number
  rotation: number
}

/** VideoRectangle：视频帧上的框，sequence 关键帧数组，帧间线性插值 */
export interface VideoRectangleValue {
  kind: 'videorectangle'
  sequence: VideoKeyframe[]
}

/** TimelineLabels：视频时间轴区间，start/end 为 1-based 帧号 inclusive */
export interface TimelineSpanValue {
  kind: 'timelinelabels'
  ranges: Array<{ start: number; end: number }>
}

/** Vector 顶点：坐标像素（serializer 转百分比），prevPointId 链表顺序 */
export interface VectorVertex {
  id: string
  x: number
  y: number
  prevPointId: string | null
  isBezier: boolean
  controlPoint1?: { x: number; y: number }
  controlPoint2?: { x: number; y: number }
}

/** Vector / VectorLabels：向量路径（折线/多边形），MVP 无贝塞尔（isBezier 全 false） */
export interface VectorValue {
  kind: 'vector'
  vertices: VectorVertex[]
  closed: boolean
}

/** Bitmask / BitmaskLabels：像素级掩码（Base64 PNG dataURL） */
export interface BitmaskValue {
  kind: 'bitmask'
  dataURL: string
  originalWidth: number
  originalHeight: number
}

/** MagicWand：魔棒 flood-fill 掩码（复用 Brush 的 RLE 编码） */
export interface MagicWandValue {
  kind: 'magicwand'
  rle: string
  originalWidth: number
  originalHeight: number
}

export type RegionValue =
  | RectangleValue
  | PolygonValue
  | KeyPointValue
  | EllipseValue
  | BrushValue
  | TextSpanValue
  | ParagraphSpanValue
  | MessageValue
  | TimeSeriesSpanValue
  | AudioSpanValue
  | VideoRectangleValue
  | TimelineSpanValue
  | VectorValue
  | BitmaskValue
  | MagicWandValue

/** 统一区域模型 — 对标 LS 的 Area 概念，value 按 kind 判别几何/区间语义 */
export interface Region {
  id: string
  /** 创建该区域的控件 name（序列化时确定 from_name / type） */
  fromName: string
  /** 单标签（Labels 类控件使用；serializer 包成数组） */
  label?: string
  /** 多态几何/区间负载 */
  value: RegionValue
  /** 该区域上挂载的 perRegion 控件结果，key = control.name */
  perRegionResults: Record<string, AnnotationResultItem>
}

export interface ImageDimensions {
  width: number
  height: number
}

export interface UseAnnotationRegionsOptions {
  taskId: string
  readOnly?: boolean
}

export interface RegionUpdate {
  label?: string
  /** 全量替换 value（与现有调用点一致，避免跨 kind 的部分合并） */
  value?: RegionValue
}

export interface UseAnnotationRegionsReturn {
  regions: Region[]
  selectedRegionId: string | null
  imageDimensions: ImageDimensions | null
  setImageDimensions: (dims: ImageDimensions | null) => void

  selectRegion: (id: string | null) => void
  addRegion: (region: Region) => void
  updateRegion: (id: string, updates: RegionUpdate) => void
  removeRegion: (id: string) => void
  undoLastRegion: () => void
  clearRegions: () => void

  getRegionResult: (regionId: string, controlName: string) => AnnotationResultItem | null
  setRegionResult: (
    regionId: string,
    controlName: string,
    result: AnnotationResultItem | null,
  ) => void

  restoreRegions: (regions: Region[]) => void
}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useAnnotationRegions(
  options: UseAnnotationRegionsOptions,
): UseAnnotationRegionsReturn {
  const { taskId, readOnly = false } = options
  const [regions, setRegions] = useState<Region[]>([])
  const [selectedRegionId, setSelectedRegionId] = useState<string | null>(null)
  const [imageDimensions, setImageDimensions] = useState<ImageDimensions | null>(null)
  const taskIdRef = useRef(taskId)

  useEffect(() => {
    if (taskIdRef.current !== taskId) {
      taskIdRef.current = taskId
      setRegions([])
      setSelectedRegionId(null)
      setImageDimensions(null)
    }
  }, [taskId])

  const selectRegion = useCallback((id: string | null) => {
    setSelectedRegionId(id)
  }, [])

  const addRegion = useCallback(
    (region: Region) => {
      if (readOnly) return
      setRegions((prev) => [...prev, region])
      setSelectedRegionId(region.id)
    },
    [readOnly],
  )

  const updateRegion = useCallback(
    (id: string, updates: RegionUpdate) => {
      if (readOnly) return
      setRegions((prev) =>
        prev.map((r) => {
          if (r.id !== id) return r
          const next: Region = { ...r }
          if (updates.label !== undefined) next.label = updates.label
          if (updates.value !== undefined) next.value = updates.value
          return next
        }),
      )
    },
    [readOnly],
  )

  const removeRegion = useCallback(
    (id: string) => {
      if (readOnly) return
      setRegions((prev) => prev.filter((r) => r.id !== id))
      setSelectedRegionId((prev) => (prev === id ? null : prev))
    },
    [readOnly],
  )

  const undoLastRegion = useCallback(() => {
    if (readOnly) return
    setRegions((prev) => prev.slice(0, -1))
    setSelectedRegionId(null)
  }, [readOnly])

  const clearRegions = useCallback(() => {
    setRegions([])
    setSelectedRegionId(null)
  }, [])

  const getRegionResult = useCallback(
    (regionId: string, controlName: string): AnnotationResultItem | null => {
      const region = regions.find((r) => r.id === regionId)
      if (!region) return null
      return region.perRegionResults[controlName] ?? null
    },
    [regions],
  )

  const setRegionResult = useCallback(
    (regionId: string, controlName: string, result: AnnotationResultItem | null) => {
      if (readOnly) return
      setRegions((prev) =>
        prev.map((r) => {
          if (r.id !== regionId) return r
          if (result) {
            return { ...r, perRegionResults: { ...r.perRegionResults, [controlName]: result } }
          }
          const next = { ...r.perRegionResults }
          delete next[controlName]
          return { ...r, perRegionResults: next }
        }),
      )
    },
    [readOnly],
  )

  const restoreRegions = useCallback((restored: Region[]) => {
    setRegions(restored)
    setSelectedRegionId(null)
  }, [])

  return useMemo(
    () => ({
      regions,
      selectedRegionId,
      imageDimensions,
      setImageDimensions,
      selectRegion,
      addRegion,
      updateRegion,
      removeRegion,
      undoLastRegion,
      clearRegions,
      getRegionResult,
      setRegionResult,
      restoreRegions,
    }),
    [
      regions,
      selectedRegionId,
      imageDimensions,
      selectRegion,
      addRegion,
      updateRegion,
      removeRegion,
      undoLastRegion,
      clearRegions,
      getRegionResult,
      setRegionResult,
      restoreRegions,
    ],
  )
}
