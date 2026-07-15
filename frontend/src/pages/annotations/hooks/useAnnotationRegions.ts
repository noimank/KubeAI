import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { AnnotationResultItem } from '@/types/annotation'

// ── Types ───────────────────────────────────────────────────────────────────

export type RegionType = 'rectangle' | 'polygon' | 'keypoint' | 'ellipse' | 'brush' | 'labels'

export interface RegionSpatial {
  x: number
  y: number
  width: number
  height: number
  rotation?: number
  /** Polygon vertices in image pixel coordinates [[x1,y1], [x2,y2], ...] */
  points?: [number, number][]
  /** Brush RLE-encoded mask string (LabelStudio format) */
  rle?: string
  /** Original image dimensions for RLE decode */
  originalWidth?: number
  originalHeight?: number
  /** Text span: character offset start (for Labels NLP control) */
  textStart?: number
  /** Text span: character offset end */
  textEnd?: number
  /** Text span: the selected text content */
  textContent?: string
}

/** 统一的空间区域数据 — 对标 LS 的 Area 模型 */
export interface AnnotationRegion {
  id: string
  type: RegionType
  /** 标签（RectangleLabels 等带标签控件使用） */
  label?: string
  /** 空间坐标（图像自然像素） */
  spatial: RegionSpatial
  /** 创建该区域的控件 name（用于序列化时确定 from_name / type） */
  sourceControlName: string
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

export interface UseAnnotationRegionsReturn {
  regions: AnnotationRegion[]
  selectedRegionId: string | null
  imageDimensions: ImageDimensions | null
  setImageDimensions: (dims: ImageDimensions | null) => void

  selectRegion: (id: string | null) => void
  addRegion: (region: AnnotationRegion) => void
  updateRegion: (id: string, updates: Partial<Pick<AnnotationRegion, 'spatial' | 'label'>>) => void
  removeRegion: (id: string) => void
  undoLastRegion: () => void
  clearRegions: () => void

  getRegionResult: (regionId: string, controlName: string) => AnnotationResultItem | null
  setRegionResult: (
    regionId: string,
    controlName: string,
    result: AnnotationResultItem | null,
  ) => void

  restoreRegions: (regions: AnnotationRegion[]) => void
}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useAnnotationRegions(
  options: UseAnnotationRegionsOptions,
): UseAnnotationRegionsReturn {
  const { taskId, readOnly = false } = options
  const [regions, setRegions] = useState<AnnotationRegion[]>([])
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
    (region: AnnotationRegion) => {
      if (readOnly) return
      setRegions((prev) => [...prev, region])
      setSelectedRegionId(region.id)
    },
    [readOnly],
  )

  const updateRegion = useCallback(
    (id: string, updates: Partial<Pick<AnnotationRegion, 'spatial' | 'label'>>) => {
      if (readOnly) return
      setRegions((prev) =>
        prev.map((r) => {
          if (r.id !== id) return r
          return {
            ...r,
            ...(updates.label !== undefined ? { label: updates.label } : {}),
            ...(updates.spatial ? { spatial: { ...r.spatial, ...updates.spatial } } : {}),
          }
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

  const restoreRegions = useCallback((restored: AnnotationRegion[]) => {
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
