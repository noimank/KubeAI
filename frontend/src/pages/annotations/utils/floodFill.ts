/**
 * Flood-fill 从种子点扩散，颜色容差阈值内连通的像素归为前景。
 * 返回单通道 mask（Uint8Array，1=前景）。供 MagicWand 生成 RLE 掩码。
 *
 * 阈值为 RGB 欧氏距离（defaultthreshold 默认 15）。使用栈避免递归爆栈。
 */
export function floodFill(
  imageData: ImageData,
  seedX: number,
  seedY: number,
  threshold: number,
): Uint8Array {
  const { data, width: w, height: h } = imageData
  const mask = new Uint8Array(w * h)
  if (seedX < 0 || seedX >= w || seedY < 0 || seedY >= h) return mask
  const seedIdx = (seedY * w + seedX) * 4
  const sr = data[seedIdx]
  const sg = data[seedIdx + 1]
  const sb = data[seedIdx + 2]
  const thr2 = threshold * threshold
  const stack: Array<[number, number]> = [[seedX, seedY]]
  while (stack.length > 0) {
    const [x, y] = stack.pop()!
    if (x < 0 || x >= w || y < 0 || y >= h) continue
    const idx = y * w + x
    if (mask[idx]) continue
    const pi = idx * 4
    const dr = data[pi] - sr
    const dg = data[pi + 1] - sg
    const db = data[pi + 2] - sb
    if (dr * dr + dg * dg + db * db > thr2) continue
    mask[idx] = 1
    stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1])
  }
  return mask
}

/** 单通道 mask → RGBA（前景 alpha=255），供 encodeRLE 编码 */
export function maskToRgba(mask: Uint8Array, width: number, height: number): Uint8ClampedArray {
  const rgba = new Uint8ClampedArray(width * height * 4)
  for (let i = 0; i < width * height; i++) {
    if (mask[i]) rgba[i * 4 + 3] = 255
  }
  return rgba
}
