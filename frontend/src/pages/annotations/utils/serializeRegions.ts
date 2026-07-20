import type { AnnotationResultItem } from '@/types/annotation'
import type { Region, RegionValue, ImageDimensions } from '../hooks/useAnnotationRegions'
import type { AnnotationRelation } from '../hooks/useAnnotationRelations'
import type { LabelStudioControlConfig, LabelStudioRelationConfig } from './parseLabelConfig'

// ── Helpers ─────────────────────────────────────────────────────────────────

function toPercent(value: number, total: number): number {
  return (value / total) * 100
}

/** control type 是否带内嵌标签（决定 value 中输出 `<type>: [label]` 键） */
function labelKey(ctrlType: string): string | null {
  return ctrlType.endsWith('labels') ? ctrlType : null
}

/** span 类 region（文本/时间/音频区间）→ LS value（无几何坐标） */
function spanValue(value: RegionValue): Record<string, unknown> {
  switch (value.kind) {
    case 'textspan':
    case 'paragraphspan':
      return { start: value.start, end: value.end, text: value.text }
    case 'timeseries':
      return { start: value.start, end: value.end, instant: value.instant }
    case 'audio':
      return { start: value.start, end: value.end }
    default:
      return {}
  }
}

/** 视频全局元数据（从 <video> loadedmetadata 采集，序列化时注入） */
export interface VideoSerializeMeta {
  framerate: number
  framesCount: number
  duration: number
}

/**
 * 视频 value → LS value。坐标本就是百分比（不经过 imageDims 的 toPercent）。
 * - videorectangle：sequence 补 time=frame/framerate + framesCount + duration
 * - timelinelabels：ranges 原样（start/end 1-based 帧号）
 */
function serializeVideo(
  value: RegionValue,
  toName: string,
  videoMetaByObject: Record<string, VideoSerializeMeta> | undefined,
): Record<string, unknown> | null {
  const meta = videoMetaByObject?.[toName]
  switch (value.kind) {
    case 'videorectangle':
      return {
        sequence: value.sequence.map((kf) => ({
          frame: kf.frame,
          enabled: kf.enabled,
          x: kf.x,
          y: kf.y,
          width: kf.width,
          height: kf.height,
          rotation: kf.rotation,
          time: meta && meta.framerate > 0 ? kf.frame / meta.framerate : 0,
        })),
        framesCount: meta?.framesCount ?? 0,
        duration: meta?.duration ?? 0,
      }
    case 'timelinelabels':
      return { ranges: value.ranges }
    default:
      return null
  }
}

/**
 * 几何 value → LS value（百分比坐标）。仅处理图像空间 kind；
 * textspan / paragraphspan / timeseries 由主流程单独处理（不需要 imageDims）。
 */
function serializeGeometry(value: RegionValue, dims: ImageDimensions): Record<string, unknown> {
  switch (value.kind) {
    case 'rectangle':
      return {
        x: toPercent(value.x, dims.width),
        y: toPercent(value.y, dims.height),
        width: toPercent(value.width, dims.width),
        height: toPercent(value.height, dims.height),
        rotation: value.rotation,
      }
    case 'polygon':
      return {
        points: value.points.map(([x, y]) => [toPercent(x, dims.width), toPercent(y, dims.height)]),
      }
    case 'keypoint':
      return {
        x: toPercent(value.x, dims.width),
        y: toPercent(value.y, dims.height),
        width: toPercent(value.width, dims.width),
      }
    case 'ellipse':
      return {
        x: toPercent(value.x, dims.width),
        y: toPercent(value.y, dims.height),
        radiusX: toPercent(value.width / 2, dims.width),
        radiusY: toPercent(value.height / 2, dims.height),
        rotation: value.rotation,
      }
    case 'brush':
      return {
        rle: value.rle,
        original_width: value.originalWidth,
        original_height: value.originalHeight,
      }
    case 'vector':
      return {
        vertices: value.vertices.map((v) => ({
          id: v.id,
          x: toPercent(v.x, dims.width),
          y: toPercent(v.y, dims.height),
          prevPointId: v.prevPointId,
          isBezier: v.isBezier,
          ...(v.controlPoint1
            ? {
                controlPoint1: {
                  x: toPercent(v.controlPoint1.x, dims.width),
                  y: toPercent(v.controlPoint1.y, dims.height),
                },
              }
            : {}),
          ...(v.controlPoint2
            ? {
                controlPoint2: {
                  x: toPercent(v.controlPoint2.x, dims.width),
                  y: toPercent(v.controlPoint2.y, dims.height),
                },
              }
            : {}),
        })),
        closed: value.closed,
      }
    case 'bitmask':
      return { imageDataURL: value.dataURL }
    case 'magicwand':
      return { format: 'rle', rle: value.rle }
    case 'textspan':
    case 'paragraphspan':
    case 'timeseries':
    case 'audio':
    case 'message':
    case 'videorectangle':
    case 'timelinelabels':
      // 由主流程处理；此处不应到达
      return {}
  }
}

/** Serialize relations into LabelStudio-compatible result items */
export function serializeRelations(
  relations: AnnotationRelation[],
  relationControls: LabelStudioRelationConfig[],
): AnnotationResultItem[] {
  const ctrlMap = new Map(relationControls.map((c) => [c.name, c]))
  return relations.map((rel) => {
    const ctrl = ctrlMap.get(rel.fromName)
    const value: Record<string, unknown> = {
      from_id: rel.fromRegionId,
      to_id: rel.toRegionId,
      direction: rel.direction ?? 'right',
    }
    if (rel.label) {
      const type = ctrl?.type ?? 'relation'
      value[type.endsWith('labels') ? type : 'labels'] = [rel.label]
    }
    return {
      id: rel.id,
      from_name: ctrl?.name ?? rel.fromName,
      to_name: ctrl?.toName ?? '',
      type: ctrl?.type ?? 'relation',
      value,
    }
  })
}

// ── Main serialize ──────────────────────────────────────────────────────────

/**
 * 将所有区域和全局分类结果序列化为 LabelStudio 兼容的 AnnotationResultItem[].
 *
 * - 空间坐标从图像像素转为百分比 (0-100)
 * - perRegion 结果共享相同区域 id
 * - 全局分类结果原样附加
 */
export function serializeRegions(
  regions: Region[],
  controls: LabelStudioControlConfig[],
  imageDims: ImageDimensions | null,
  globalResults: Record<string, AnnotationResultItem[]>,
  relations?: AnnotationRelation[],
  relationControls?: LabelStudioRelationConfig[],
  videoMetaByObject?: Record<string, VideoSerializeMeta>,
): AnnotationResultItem[] {
  const results: AnnotationResultItem[] = []
  const controlMap = new Map(controls.map((c) => [c.name, c]))

  for (const region of regions) {
    const ctrl = controlMap.get(region.fromName)
    const isTextLike = region.value.kind === 'textspan' || region.value.kind === 'paragraphspan'
    const isTimeSpan = region.value.kind === 'timeseries'
    const isAudioSpan = region.value.kind === 'audio'
    const isVideoRect = region.value.kind === 'videorectangle'
    const isTimeline = region.value.kind === 'timelinelabels'

    if (ctrl && (isVideoRect || isTimeline)) {
      // 视频 region：百分比坐标独立序列化（不经过 imageDims）
      const value = serializeVideo(region.value, ctrl.toName, videoMetaByObject)
      if (value) {
        const lk = labelKey(ctrl.type) ?? 'labels' // videorectangle→labels, timelinelabels→timelinelabels
        if (region.label) value[lk] = [region.label]
        results.push({
          id: region.id,
          from_name: ctrl.name,
          to_name: ctrl.toName,
          type: ctrl.type,
          value,
        })
      }
    } else if (ctrl && (isTextLike || isTimeSpan || isAudioSpan)) {
      // 文本 span / 时间区间（Labels / HyperTextLabels / ParagraphLabels / TimeSeriesLabels）— 不需 imageDims
      const value = spanValue(region.value)
      const lk = labelKey(ctrl.type) ?? 'labels'
      if (region.label) value[lk] = [region.label]
      results.push({
        id: region.id,
        from_name: ctrl.name,
        to_name: ctrl.toName,
        type: ctrl.type,
        value,
      })
    } else if (ctrl && imageDims) {
      const value = serializeGeometry(region.value, imageDims)
      const lk = labelKey(ctrl.type)
      if (lk && region.label) value[lk] = [region.label]
      results.push({
        id: region.id,
        from_name: ctrl.name,
        to_name: ctrl.toName,
        type: ctrl.type,
        value,
      })
    }
    // message 区域：fromName 为 Chat 对象名（无对应 ctrl），不产出几何结果，
    // 仅其上的 perRegion 控件结果会序列化（共享 message 区域 id）。

    // perRegion 结果共享同一个区域 id（即使几何未序列化也保留）
    for (const resultItem of Object.values(region.perRegionResults)) {
      results.push({ ...resultItem, id: region.id })
    }
  }

  // 全局分类结果
  for (const items of Object.values(globalResults)) {
    results.push(...items)
  }

  // 关系标注
  if (relations && relationControls && relations.length > 0) {
    results.push(...serializeRelations(relations, relationControls))
  }

  return results
}
