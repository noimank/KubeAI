import type { VideoKeyframe } from '../../hooks/useAnnotationRegions'

/** 线性插值 */
export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

/** 角度归一化到 [-180, 180) */
function normalizeAngle(a: number): number {
  let r = a % 360
  if (r >= 180) r -= 360
  if (r < -180) r += 360
  return r
}

/** 角度最短弧插值（对标 LS interpolateProp） */
export function lerpAngle(a: number, b: number, t: number): number {
  const delta = normalizeAngle(b - a)
  return normalizeAngle(a + delta * t)
}

/** frame -> time（秒），framerate 非正时返回 0 */
export function frameToTime(frame: number, framerate: number): number {
  return framerate > 0 ? frame / framerate : 0
}

/**
 * 计算 sequence 在指定帧的形状（插值）。返回 null 表示该帧不可见：
 *  - frame 早于第一个关键帧
 *  - lifespan 中最近一个关键帧 enabled=false（从该帧起隐藏，直到下一个 enabled=true）
 *
 * 命中关键帧返回该点；两个关键帧之间线性插值（rotation 走最短弧）；
 * 最后一个关键帧之后保持。
 */
export function getShapeAtFrame(sequence: VideoKeyframe[], frame: number): VideoKeyframe | null {
  if (sequence.length === 0) return null
  const sorted = sequence.slice().sort((a, b) => a.frame - b.frame)
  if (frame < sorted[0].frame) return null

  // lifespan：frame <= 当前的最后一个关键帧；若其 enabled=false 则隐藏
  let lastAtOrBefore = sorted[0]
  for (const kf of sorted) {
    if (kf.frame <= frame) lastAtOrBefore = kf
    else break
  }
  if (!lastAtOrBefore.enabled) return null

  const last = sorted[sorted.length - 1]
  if (frame >= last.frame) return last

  const next = sorted.find((k) => k.frame > frame)!
  const t = (frame - lastAtOrBefore.frame) / (next.frame - lastAtOrBefore.frame)
  return {
    frame,
    enabled: true,
    x: lerp(lastAtOrBefore.x, next.x, t),
    y: lerp(lastAtOrBefore.y, next.y, t),
    width: lerp(lastAtOrBefore.width, next.width, t),
    height: lerp(lastAtOrBefore.height, next.height, t),
    rotation: lerpAngle(lastAtOrBefore.rotation, next.rotation, t),
  }
}

/** 该 region 在任意帧是否有可见关键帧段（用于列表展示） */
export function hasVisibleSpan(sequence: VideoKeyframe[]): boolean {
  return sequence.some((kf) => kf.enabled)
}
