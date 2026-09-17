import type { AnnotationResultItem } from '@/types/annotation'
import type { Region, VideoKeyframe } from '../hooks/useAnnotationRegions'
import { generateId } from './id'

/**
 * 将 task.result 反序列化为 Region[]，供 workspace 只读回显。
 *
 * MVP 覆盖无需 imageDims 的 kind：videorectangle / timelinelabels / timeseries /
 * audio / textspan（labels/hypertextlabels）。图像几何 kind（rectangle/polygon/
 * keypoint/ellipse/brush）存像素坐标而 result 是百分比，转换需 imageDims，留作增强。
 * perRegionResults 不在此恢复（需按 region id 聚合，单独处理）。
 */
export function deserializeRegions(results: AnnotationResultItem[] | null | undefined): Region[] {
  if (!results || results.length === 0) return []
  const regions: Region[] = []
  for (const item of results) {
    const v = (item.value ?? {}) as Record<string, unknown>
    const id = item.id ?? generateId()
    const fromName = item.from_name
    const label = firstLabel(v, item.type)
    const region = buildRegion(item.type, v, id, fromName, label)
    if (region) regions.push(region)
  }
  return regions
}

function num(x: unknown, d = 0): number {
  return typeof x === 'number' ? x : Number(x) || d
}

function firstLabel(v: Record<string, unknown>, type: string): string | undefined {
  const key = type.endsWith('labels') ? type : 'labels'
  const arr = v[key] as string[] | undefined
  return arr?.[0]
}

function parseSequence(raw: unknown): VideoKeyframe[] {
  if (!Array.isArray(raw)) return []
  return raw
    .map((k): VideoKeyframe => {
      const kf = k as Record<string, unknown>
      return {
        frame: Number(kf.frame) || 1,
        enabled: kf.enabled !== false,
        x: num(kf.x),
        y: num(kf.y),
        width: num(kf.width),
        height: num(kf.height),
        rotation: num(kf.rotation),
      }
    })
    .sort((a, b) => a.frame - b.frame)
}

function buildRegion(
  type: string,
  v: Record<string, unknown>,
  id: string,
  fromName: string,
  label: string | undefined,
): Region | null {
  const perRegionResults: Record<string, AnnotationResultItem> = {}
  switch (type) {
    case 'labels':
    case 'hypertextlabels': {
      // labels 控件用于 NER（有 text）或 Audio（无 text）
      if (typeof v.text === 'string') {
        return {
          id,
          fromName,
          label,
          value: { kind: 'textspan', start: num(v.start), end: num(v.end), text: v.text },
          perRegionResults,
        }
      }
      return {
        id,
        fromName,
        label,
        value: { kind: 'audio', start: num(v.start), end: num(v.end) },
        perRegionResults,
      }
    }
    case 'timeserieslabels':
      return {
        id,
        fromName,
        label,
        value: {
          kind: 'timeseries',
          start: num(v.start),
          end: num(v.end),
          instant: v.instant === true,
        },
        perRegionResults,
      }
    case 'videorectangle':
      return {
        id,
        fromName,
        label,
        value: { kind: 'videorectangle', sequence: parseSequence(v.sequence) },
        perRegionResults,
      }
    case 'timelinelabels': {
      const ranges = Array.isArray(v.ranges)
        ? v.ranges.map((r) => {
            const rr = r as Record<string, unknown>
            return { start: Number(rr.start) || 1, end: Number(rr.end) || 1 }
          })
        : []
      return { id, fromName, label, value: { kind: 'timelinelabels', ranges }, perRegionResults }
    }
    default:
      return null
  }
}
