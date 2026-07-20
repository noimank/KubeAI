import { describe, it, expect } from 'vitest'
import {
  getShapeAtFrame,
  lerp,
  lerpAngle,
  frameToTime,
} from '@/pages/annotations/components/video/videoMath'
import type { VideoKeyframe } from '@/pages/annotations/hooks/useAnnotationRegions'

function kf(frame: number, overrides: Partial<VideoKeyframe> = {}): VideoKeyframe {
  return { frame, enabled: true, x: 0, y: 0, width: 10, height: 10, rotation: 0, ...overrides }
}

describe('videoMath', () => {
  describe('lerp', () => {
    it('线性插值端点与中点', () => {
      expect(lerp(0, 10, 0)).toBe(0)
      expect(lerp(0, 10, 0.5)).toBe(5)
      expect(lerp(0, 10, 1)).toBe(10)
    })
  })

  describe('lerpAngle', () => {
    it('走最短弧（350→10 经 0 而非绕大圈）', () => {
      expect(lerpAngle(350, 10, 0.5)).toBe(0)
      expect(lerpAngle(0, 90, 0.5)).toBe(45)
    })
  })

  describe('frameToTime', () => {
    it('frame / framerate', () => {
      expect(frameToTime(25, 25)).toBe(1)
      expect(frameToTime(1, 24)).toBeCloseTo(1 / 24)
      expect(frameToTime(1, 0)).toBe(0)
    })
  })

  describe('getShapeAtFrame', () => {
    it('空 sequence 返回 null', () => {
      expect(getShapeAtFrame([], 1)).toBeNull()
    })

    it('frame 早于第一个关键帧返回 null', () => {
      expect(getShapeAtFrame([kf(5)], 1)).toBeNull()
    })

    it('命中关键帧返回该点', () => {
      const a = kf(5, { x: 10 })
      expect(getShapeAtFrame([a], 5)).toEqual(a)
    })

    it('最后关键帧之后保持', () => {
      const a = kf(5, { x: 10 })
      expect(getShapeAtFrame([a], 100)).toEqual(a)
    })

    it('两关键帧之间线性插值（中点）', () => {
      const shape = getShapeAtFrame([kf(1, { x: 0 }), kf(11, { x: 100 })], 6)!
      expect(shape.x).toBe(50)
    })

    it('enabled=false 隐藏后续帧直到下一个 enabled=true', () => {
      const seq = [kf(1, { enabled: true }), kf(5, { enabled: false }), kf(10, { enabled: true })]
      expect(getShapeAtFrame(seq, 3)).not.toBeNull()
      expect(getShapeAtFrame(seq, 7)).toBeNull()
      expect(getShapeAtFrame(seq, 12)).not.toBeNull()
    })

    it('rotation 跨 0° 边界走最短弧', () => {
      const shape = getShapeAtFrame([kf(1, { rotation: 350 }), kf(11, { rotation: 10 })], 6)!
      expect(shape.rotation).toBe(0)
    })

    it('sequence 无序时按 frame 排序', () => {
      const shape = getShapeAtFrame([kf(11, { x: 100 }), kf(1, { x: 0 })], 6)!
      expect(shape.x).toBe(50)
    })
  })
})
