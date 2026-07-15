import { useEffect, useRef, useState } from 'react'
import { appendAuthToken } from '@/utils/constants'

interface RegionCropPreviewProps {
  /** Image URL (without token — will be appended internally) */
  imageUrl: string
  /** Selected region spatial in image-pixel coordinates */
  spatial: { x: number; y: number; width: number; height: number }
  /** Natural image dimensions */
  imageWidth: number
  imageHeight: number
  /** Container height (default 140) */
  height?: number
}

/**
 * Displays a zoomed-in crop of the selected annotation region.
 *
 * Mimics Label Studio's per-region preview: the image is scaled and offset so
 * the bounding box of the selected region is centered and fills the container.
 *
 * Falls back to a plain <img> while the image is still loading; if image
 * natural dimensions don't match imageWidth/imageHeight the crop may be offset
 * — this is expected behavior for resized images.
 */
export default function RegionCropPreview({
  imageUrl,
  spatial,
  imageWidth,
  imageHeight,
  height = 140,
}: RegionCropPreviewProps) {
  const imgRef = useRef<HTMLImageElement | null>(null)
  const containerRef = useRef<HTMLDivElement | null>(null)
  const [containerWidth, setContainerWidth] = useState(280)
  const [loaded, setLoaded] = useState(false)

  // Track container width for responsive scale
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setContainerWidth(entry.contentRect.width)
      }
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  // Preload image to get natural dimensions
  useEffect(() => {
    let cancelled = false
    const img = new window.Image()
    img.crossOrigin = 'anonymous'
    img.src = appendAuthToken(imageUrl)
    img.onload = () => {
      if (!cancelled) {
        imgRef.current = img
        setLoaded(true)
      }
    }
    img.onerror = () => {
      if (!cancelled) setLoaded(false)
    }
    return () => {
      cancelled = true
    }
  }, [imageUrl])

  // Guard against zero-dimension regions
  if (spatial.width <= 0 || spatial.height <= 0) {
    return (
      <div
        style={{
          width: '100%',
          height,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          border: '1px solid var(--ant-color-border)',
          borderRadius: 6,
          background: 'var(--ant-color-bg-layout)',
        }}
      >
        <span style={{ color: 'var(--ant-color-text-secondary)', fontSize: 12 }}>区域尺寸无效</span>
      </div>
    )
  }

  // Calculate scale: region fills ~85% of container in whichever dimension is
  // more constrained, so the entire region is visible.
  const padding = 16 // px padding inside container
  const availW = Math.max(1, containerWidth - padding * 2)
  const availH = Math.max(1, height - padding * 2)
  const scale = Math.min(availW / spatial.width, availH / spatial.height)

  // Center the region in the container
  const offsetX = (containerWidth - spatial.width * scale) / 2
  const offsetY = (height - spatial.height * scale) / 2

  // The image is positioned so the region appears at (offsetX, offsetY)
  const imgTranslateX = offsetX - spatial.x * scale
  const imgTranslateY = offsetY - spatial.y * scale

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height,
        overflow: 'hidden',
        position: 'relative',
        borderRadius: 6,
        border: '1px solid var(--ant-color-border)',
        background: 'var(--ant-color-bg-layout)',
      }}
    >
      {loaded && imgRef.current ? (
        <img
          src={imgRef.current.src}
          alt="选中区域"
          style={{
            position: 'absolute',
            width: imageWidth * scale,
            height: imageHeight * scale,
            transform: `translate(${imgTranslateX}px, ${imgTranslateY}px)`,
            transformOrigin: 'top left',
            pointerEvents: 'none',
          }}
        />
      ) : (
        <div
          style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <span style={{ color: 'var(--ant-color-text-secondary)', fontSize: 12 }}>加载中…</span>
        </div>
      )}
      {/* Region label badge */}
      <div
        style={{
          position: 'absolute',
          top: 4,
          left: 4,
          padding: '1px 6px',
          fontSize: 11,
          background: 'rgba(22, 119, 255, 0.85)',
          color: '#fff',
          borderRadius: 4,
          lineHeight: '18px',
        }}
      >
        {Math.round(spatial.width)} × {Math.round(spatial.height)}
      </div>
    </div>
  )
}
