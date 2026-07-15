/**
 * LabelStudio-compatible RLE (Run-Length Encoding) for brush masks.
 *
 * Format: space-separated integers where even indices (0-based) are counts of
 * background pixels (0) and odd indices are counts of foreground pixels (1).
 * The sequence always starts with background pixels — if the mask starts with
 * foreground pixels, the first value is 0.
 */

/**
 * Encode a binary mask (Uint8ClampedArray where any non-zero value = foreground)
 * into a LabelStudio-compatible RLE string.
 *
 * @param mask - RGBA pixel data from canvas getImageData
 * @param width - Image width in pixels
 * @param height - Image height in pixels
 * @returns RLE-encoded string of space-separated integers
 */
export function encodeRLE(mask: Uint8ClampedArray, width: number, height: number): string {
  const runs: number[] = []
  let current = 0 // 0 = background, 1 = foreground
  let count = 0

  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      // RGBA pixel: check alpha channel (index 3)
      const alpha = mask[(y * width + x) * 4 + 3]
      const pixel = alpha > 0 ? 1 : 0

      if (pixel === current) {
        count++
      } else {
        runs.push(count)
        current = pixel
        count = 1
      }
    }
  }
  // Push final run
  runs.push(count)

  return runs.join(' ')
}

/**
 * Decode a LabelStudio RLE string into pixel data for rendering.
 *
 * @param rle - RLE-encoded string
 * @param width - Original image width
 * @param height - Original image height
 * @returns HTMLImageData-compatible object ready for putImageData
 */
export function decodeRLE(rle: string, width: number, height: number): ImageData {
  const runs = rle.trim().split(/\s+/).map(Number)
  const data = new Uint8ClampedArray(width * height * 4)
  let x = 0
  let y = 0
  let onPixel = false // starts background

  for (const run of runs) {
    if (onPixel) {
      for (let i = 0; i < run && y < height; i++) {
        const idx = (y * width + x) * 4
        data[idx] = 0 // R
        data[idx + 1] = 0 // G
        data[idx + 2] = 0 // B
        data[idx + 3] = 255 // A
        x++
        if (x >= width) {
          x = 0
          y++
        }
      }
    } else {
      // Skip background pixels
      const totalSkip = run
      const remainingInRow = width - x
      if (totalSkip <= remainingInRow) {
        x += totalSkip
      } else {
        const skipAfterRow = totalSkip - remainingInRow
        y += Math.floor(skipAfterRow / width) + 1
        x = skipAfterRow % width
      }
    }
    onPixel = !onPixel
  }

  return new ImageData(data, width, height)
}
