import { describe, it, expect } from 'vitest'
import { floodFill, maskToRgba } from '@/pages/annotations/utils/floodFill'

function makeImageData(
  width: number,
  height: number,
  fillFn: (x: number, y: number) => [number, number, number],
): ImageData {
  const data = new Uint8ClampedArray(width * height * 4)
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4
      const [r, g, b] = fillFn(x, y)
      data[i] = r
      data[i + 1] = g
      data[i + 2] = b
      data[i + 3] = 255
    }
  }
  return { data, width, height } as ImageData
}

describe('floodFill', () => {
  it('全图同色 → 全部选中', () => {
    const img = makeImageData(5, 5, () => [100, 100, 100])
    const mask = floodFill(img, 2, 2, 10)
    expect(mask.every((v) => v === 1)).toBe(true)
  })

  it('色差超阈值的区域不选中', () => {
    const img = makeImageData(5, 5, (x) => (x < 3 ? [100, 100, 100] : [200, 200, 200]))
    const mask = floodFill(img, 0, 0, 10)
    expect(mask[0]).toBe(1) // 种子点 (0,0)
    expect(mask[4]).toBe(0) // (4,0) 右侧异色
    expect(mask[2]).toBe(1) // (2,0) 边界同色仍选中
  })

  it('越界种子返回空 mask', () => {
    const img = makeImageData(3, 3, () => [0, 0, 0])
    const mask = floodFill(img, 10, 10, 10)
    expect(mask.every((v) => v === 0)).toBe(true)
  })
})

describe('maskToRgba', () => {
  it('前景 alpha=255，背景 alpha=0', () => {
    const mask = new Uint8Array([1, 0, 1])
    const rgba = maskToRgba(mask, 3, 1)
    expect(rgba[3]).toBe(255)
    expect(rgba[7]).toBe(0)
    expect(rgba[11]).toBe(255)
  })
})
