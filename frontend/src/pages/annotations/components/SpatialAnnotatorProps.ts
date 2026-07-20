import type { AnnotationTask } from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import type { Region, ImageDimensions, RegionUpdate } from '../hooks/useAnnotationRegions'
import type { AnnotationRelation } from '../hooks/useAnnotationRelations'

/** 所有空间标注器共享的 props 接口 — 统一委托给 useAnnotationRegions 管理状态 */
export interface SpatialAnnotatorProps {
  task: AnnotationTask
  objectConfig?: LabelStudioObjectConfig
  controlConfig: LabelStudioControlConfig
  readOnly?: boolean
  /** useAnnotationRegions — 共享区域数据 */
  regions: Region[]
  selectedRegionId: string | null
  imageDimensions: ImageDimensions | null
  onAddRegion: (region: Region) => void
  onUpdateRegion: (id: string, updates: RegionUpdate) => void
  onDeleteRegion: (id: string) => void
  onSelectRegion: (id: string | null) => void
  onImageDimensionsChange: (dims: ImageDimensions) => void
  /** 关系标注（可选 — 仅 Image 空间标注器渲染箭头） */
  relations?: AnnotationRelation[]
}
