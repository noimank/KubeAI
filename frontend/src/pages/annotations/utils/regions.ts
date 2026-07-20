import type { Region, RegionValue } from '../hooks/useAnnotationRegions'

/**
 * 按 fromName + value.kind 窄化过滤区域。返回类型自动收敛到对应 kind 的 Region 子集，
 * 调用方无需再做 `as` 断言即可直接读取几何字段。
 */
export function regionsOf<K extends RegionValue['kind']>(
  regions: Region[],
  fromName: string,
  kind: K,
): Array<Region & { value: Extract<RegionValue, { kind: K }> }> {
  return regions.filter(
    (r): r is Region & { value: Extract<RegionValue, { kind: K }> } =>
      r.fromName === fromName && r.value.kind === kind,
  )
}

export interface BBox {
  x: number
  y: number
  width: number
  height: number
}

/**
 * 计算区域在图像像素坐标系下的包围盒（用于 RegionCropPreview / 关系箭头定位）。
 * 文本 span 无图像坐标，返回 null。
 */
export function regionBoundingBox(region: Region): BBox | null {
  return valueBoundingBox(region.value)
}

export function valueBoundingBox(value: RegionValue): BBox | null {
  switch (value.kind) {
    case 'rectangle':
    case 'ellipse':
      return { x: value.x, y: value.y, width: value.width, height: value.height }
    case 'keypoint':
      return {
        x: value.x - value.width / 2,
        y: value.y - value.width / 2,
        width: value.width,
        height: value.width,
      }
    case 'polygon': {
      if (value.points.length === 0) return null
      const xs = value.points.map((p) => p[0])
      const ys = value.points.map((p) => p[1])
      const minX = Math.min(...xs)
      const minY = Math.min(...ys)
      return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY }
    }
    case 'brush':
      return { x: 0, y: 0, width: value.originalWidth, height: value.originalHeight }
    case 'vector': {
      if (value.vertices.length === 0) return null
      const xs = value.vertices.map((v) => v.x)
      const ys = value.vertices.map((v) => v.y)
      const minX = Math.min(...xs)
      const minY = Math.min(...ys)
      return { x: minX, y: minY, width: Math.max(...xs) - minX, height: Math.max(...ys) - minY }
    }
    case 'bitmask':
      return { x: 0, y: 0, width: value.originalWidth, height: value.originalHeight }
    case 'magicwand':
      return { x: 0, y: 0, width: value.originalWidth, height: value.originalHeight }
    case 'textspan':
    case 'paragraphspan':
    case 'message':
    case 'timeseries':
    case 'audio':
    case 'videorectangle':
    case 'timelinelabels':
      return null
  }
}

/** 区域包围盒中心点（关系箭头起止用） */
export function regionCenter(region: Region): { x: number; y: number } | null {
  const bb = regionBoundingBox(region)
  if (!bb) return null
  return { x: bb.x + bb.width / 2, y: bb.y + bb.height / 2 }
}
