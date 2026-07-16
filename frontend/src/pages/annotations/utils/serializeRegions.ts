import type { AnnotationResultItem } from '@/types/annotation'
import type { AnnotationRegion, ImageDimensions } from '../hooks/useAnnotationRegions'
import type { AnnotationRelation } from '../hooks/useAnnotationRelations'
import type { LabelStudioControlConfig, LabelStudioRelationConfig } from './parseLabelConfig'

// ── Helpers ─────────────────────────────────────────────────────────────────

function toPercent(value: number, total: number): number {
  return (value / total) * 100
}

/** 根据 control type 生成结果 value 中的标签键名 */
function labelKey(ctrlType: string): string | null {
  if (ctrlType.endsWith('labels')) return ctrlType
  return null
}

// ── Per-geometry serialization ──────────────────────────────────────────────

function serializeRectangleRegion(
  region: AnnotationRegion,
  _ctrl: LabelStudioControlConfig,
  dims: ImageDimensions,
): Record<string, unknown> {
  return {
    x: toPercent(region.spatial.x, dims.width),
    y: toPercent(region.spatial.y, dims.height),
    width: toPercent(region.spatial.width, dims.width),
    height: toPercent(region.spatial.height, dims.height),
    rotation: region.spatial.rotation ?? 0,
  }
}

function serializePolygonRegion(
  region: AnnotationRegion,
  _ctrl: LabelStudioControlConfig,
  dims: ImageDimensions,
): Record<string, unknown> {
  const points = region.spatial.points ?? []
  return {
    points: points.map(([x, y]) => [toPercent(x, dims.width), toPercent(y, dims.height)]),
  }
}

function serializeKeyPointRegion(
  region: AnnotationRegion,
  _ctrl: LabelStudioControlConfig,
  dims: ImageDimensions,
): Record<string, unknown> {
  return {
    x: toPercent(region.spatial.x, dims.width),
    y: toPercent(region.spatial.y, dims.height),
    width: toPercent(region.spatial.width, dims.width),
  }
}

function serializeEllipseRegion(
  region: AnnotationRegion,
  _ctrl: LabelStudioControlConfig,
  dims: ImageDimensions,
): Record<string, unknown> {
  return {
    x: toPercent(region.spatial.x, dims.width),
    y: toPercent(region.spatial.y, dims.height),
    radiusX: toPercent(region.spatial.width / 2, dims.width),
    radiusY: toPercent(region.spatial.height / 2, dims.height),
    rotation: region.spatial.rotation ?? 0,
  }
}

function serializeBrushRegion(
  region: AnnotationRegion,
  _ctrl: LabelStudioControlConfig,
  _dims: ImageDimensions,
): Record<string, unknown> {
  return {
    rle: region.spatial.rle ?? '',
    original_width: region.spatial.originalWidth ?? 0,
    original_height: region.spatial.originalHeight ?? 0,
  }
}

/** Serialize text span region (Labels NLP control) */
function serializeLabelsRegion(region: AnnotationRegion): Record<string, unknown> {
  return {
    start: region.spatial.textStart ?? 0,
    end: region.spatial.textEnd ?? 0,
    text: region.spatial.textContent ?? '',
  }
}

/** Serialize relations into LabelStudio-compatible result items */
export function serializeRelations(
  relations: AnnotationRelation[],
  relationControls: LabelStudioRelationConfig[],
): AnnotationResultItem[] {
  const ctrlMap = new Map(relationControls.map((c) => [c.name, c]))
  return relations.map((rel) => {
    const ctrl = ctrlMap.get(rel.sourceControlName)
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
      from_name: ctrl?.name ?? rel.sourceControlName,
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
  regions: AnnotationRegion[],
  controls: LabelStudioControlConfig[],
  imageDims: ImageDimensions | null,
  globalResults: Record<string, AnnotationResultItem[]>,
  relations?: AnnotationRelation[],
  relationControls?: LabelStudioRelationConfig[],
): AnnotationResultItem[] {
  const results: AnnotationResultItem[] = []
  const controlMap = new Map(controls.map((c) => [c.name, c]))
  const SERIALIZERS: Record<
    string,
    (
      r: AnnotationRegion,
      ctrl: LabelStudioControlConfig,
      dims: ImageDimensions,
    ) => Record<string, unknown>
  > = {
    rectangle: serializeRectangleRegion,
    rectanglelabels: serializeRectangleRegion,
    polygon: serializePolygonRegion,
    polygonlabels: serializePolygonRegion,
    keypoint: serializeKeyPointRegion,
    keypointlabels: serializeKeyPointRegion,
    ellipse: serializeEllipseRegion,
    ellipselabels: serializeEllipseRegion,
    brush: serializeBrushRegion,
    brushlabels: serializeBrushRegion,
  }

  for (const region of regions) {
    const areaId = region.id
    const sourceCtrl = controlMap.get(region.sourceControlName)

    // Text span regions (Labels control) don't need image dimensions
    if (sourceCtrl?.type === 'labels') {
      const value = serializeLabelsRegion(region)
      if (region.label) {
        value.labels = [region.label]
      }
      results.push({
        id: areaId,
        from_name: sourceCtrl.name,
        to_name: sourceCtrl.toName,
        type: 'labels',
        value,
      })
      // perRegion results
      for (const resultItem of Object.values(region.perRegionResults)) {
        results.push({ ...resultItem, id: areaId })
      }
      continue
    }

    if (sourceCtrl && imageDims && SERIALIZERS[sourceCtrl.type]) {
      const value = SERIALIZERS[sourceCtrl.type](region, sourceCtrl, imageDims)

      // 附加标签（仅 Labels 变体）
      const lk = labelKey(sourceCtrl.type)
      if (lk && region.label) {
        value[lk] = [region.label]
      }

      results.push({
        id: areaId,
        from_name: sourceCtrl.name,
        to_name: sourceCtrl.toName,
        type: sourceCtrl.type,
        value,
      })
    }

    // perRegion 结果共享同一个 area id
    for (const resultItem of Object.values(region.perRegionResults)) {
      results.push({ ...resultItem, id: areaId })
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
