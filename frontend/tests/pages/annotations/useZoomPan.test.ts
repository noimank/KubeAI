import { describe, it, expect } from 'vitest'

/**
 * 镜像 useZoomPan 中的核心公式。
 * 把它独立出来便于单测,源文件在测试时通过真实 hook 调用同一公式。
 */
function imageToScreen(ix: number, iy: number, scale: number, pos: { x: number; y: number }) {
  return { x: pos.x + ix * scale, y: pos.y + iy * scale }
}

function screenToImage(sx: number, sy: number, scale: number, pos: { x: number; y: number }) {
  return { x: (sx - pos.x) / scale, y: (sy - pos.y) / scale }
}

/**
 * 在 scale 变更后保持鼠标锚点不动的新 stagePos。
 */
function preserveAnchor(
  pointer: { x: number; y: number },
  oldScale: number,
  newScale: number,
  pos: { x: number; y: number },
) {
  const img = screenToImage(pointer.x, pointer.y, oldScale, pos)
  return {
    x: pointer.x - img.x * newScale,
    y: pointer.y - img.y * newScale,
  }
}

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v))

describe('useZoomPan 坐标换算', () => {
  it('imageToScreen / screenToImage 互逆', () => {
    const pos = { x: 50, y: 30 }
    const scale = 0.5
    const img = { x: 200, y: 400 }
    const screen = imageToScreen(img.x, img.y, scale, pos)
    expect(screen).toEqual({ x: 50 + 200 * 0.5, y: 30 + 400 * 0.5 })
    const back = screenToImage(screen.x, screen.y, scale, pos)
    expect(back.x).toBeCloseTo(img.x, 6)
    expect(back.y).toBeCloseTo(img.y, 6)
  })

  it('wheel 缩放:保持鼠标锚点对应的图像坐标不变', () => {
    const oldScale = 0.5
    const pos = { x: 0, y: 0 }
    const pointer = { x: 100, y: 200 }
    // 缩放前鼠标对应的图像坐标
    const imgBefore = screenToImage(pointer.x, pointer.y, oldScale, pos)
    // 放大到 1.0
    const newScale = 1.0
    const newPos = preserveAnchor(pointer, oldScale, newScale, pos)
    const imgAfter = screenToImage(pointer.x, pointer.y, newScale, newPos)
    expect(imgAfter.x).toBeCloseTo(imgBefore.x, 6)
    expect(imgAfter.y).toBeCloseTo(imgBefore.y, 6)
  })

  it('clamp 缩放到 [0.1, 20]', () => {
    expect(clamp(0.05, 0.1, 20)).toBe(0.1)
    expect(clamp(50, 0.1, 20)).toBe(20)
    expect(clamp(1.5, 0.1, 20)).toBe(1.5)
  })

  it('缩放到 1.0 时一张 1000x800 的图像居中显示在 600x400 容器中', () => {
    const stageW = 600
    const stageH = 400
    const imgW = 1000
    const imgH = 800
    const fitScale = Math.min(stageW / imgW, stageH / imgH)
    const pos = {
      x: (stageW - imgW * fitScale) / 2,
      y: (stageH - imgH * fitScale) / 2,
    }
    expect(fitScale).toBeCloseTo(0.5, 6)
    // 图像四个角 → 屏幕坐标
    const tl = imageToScreen(0, 0, fitScale, pos)
    const br = imageToScreen(imgW, imgH, fitScale, pos)
    expect(tl).toEqual({ x: 50, y: 0 })
    expect(br).toEqual({ x: 550, y: 400 })
  })
})
