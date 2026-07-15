import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Slider, Space, Tag, Typography } from 'antd'
import {
  DeleteOutlined,
  UndoOutlined,
  ClearOutlined,
  FormatPainterOutlined,
} from '@ant-design/icons'
import { Image as KonvaImage } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import { encodeRLE } from '../utils/rleEncoder'
import type { AnnotationRegion } from '../hooks/useAnnotationRegions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'

// ── Constants ───────────────────────────────────────────────────────────────
const DEFAULT_BRUSH_SIZE = 20
const MIN_BRUSH_SIZE = 2
const MAX_BRUSH_SIZE = 80

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Draw a filled circle on a 2D canvas context */
function drawBrushDot(ctx: CanvasRenderingContext2D, x: number, y: number, radius: number) {
  ctx.beginPath()
  ctx.arc(x, y, radius, 0, Math.PI * 2)
  ctx.fill()
}

/** Draw a line between two points (interpolated brush strokes) */
function drawBrushLine(
  ctx: CanvasRenderingContext2D,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  radius: number,
) {
  const dx = x1 - x0
  const dy = y1 - y0
  const dist = Math.sqrt(dx * dx + dy * dy)
  const step = radius * 0.5
  if (dist < step) {
    drawBrushDot(ctx, x1, y1, radius)
    return
  }
  const steps = Math.ceil(dist / step)
  for (let i = 0; i <= steps; i++) {
    const t = i / steps
    drawBrushDot(ctx, x0 + dx * t, y0 + dy * t, radius)
  }
}

// ── Component ───────────────────────────────────────────────────────────────

export default function BrushAnnotator({
  task,
  objectConfig,
  controlConfig,
  readOnly = false,
  regions,
  selectedRegionId,
  imageDimensions,
  onAddRegion,
  onDeleteRegion,
  onSelectRegion,
  onImageDimensionsChange,
}: SpatialAnnotatorProps) {
  const hasLabels = controlConfig.type === 'brushlabels'
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined
  const zp = useZoomPan(imageUrl)

  const [brushSize, setBrushSize] = useState(DEFAULT_BRUSH_SIZE)
  const [activeLabel, setActiveLabel] = useState<string | null>(
    hasLabels ? (controlConfig.choices[0]?.value ?? null) : null,
  )
  const [isDrawing, setIsDrawing] = useState(false)
  const [hasUnsavedMask, setHasUnsavedMask] = useState(false)

  // Offscreen canvas for mask accumulation
  const maskCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const maskCtxRef = useRef<CanvasRenderingContext2D | null>(null)
  const lastPointRef = useRef<{ x: number; y: number } | null>(null)
  // Konva Image node ref for updating the displayed mask
  const maskImageRef = useRef<Konva.Image | null>(null)

  // Reset on task change
  useEffect(() => {
    setHasUnsavedMask(false)
    lastPointRef.current = null
    if (hasLabels) setActiveLabel(controlConfig.choices[0]?.value ?? null)
    // Clear mask canvas
    if (maskCtxRef.current && maskCanvasRef.current) {
      maskCtxRef.current.clearRect(0, 0, maskCanvasRef.current.width, maskCanvasRef.current.height)
    }
  }, [task.id, hasLabels, controlConfig.choices])

  // Initialize mask canvas when image dimensions are known
  useEffect(() => {
    if (zp.image && !imageDimensions) {
      onImageDimensionsChange({ width: zp.image.width, height: zp.image.height })
    }
    if (zp.image && imageDimensions) {
      if (
        !maskCanvasRef.current ||
        maskCanvasRef.current.width !== imageDimensions.width ||
        maskCanvasRef.current.height !== imageDimensions.height
      ) {
        const canvas = document.createElement('canvas')
        canvas.width = imageDimensions.width
        canvas.height = imageDimensions.height
        maskCanvasRef.current = canvas
        const ctx = canvas.getContext('2d')
        if (ctx) {
          ctx.fillStyle = 'rgba(0,0,0,1)'
          maskCtxRef.current = ctx
        }
      }
    }
  }, [zp.image, imageDimensions, onImageDimensionsChange])

  // Filter brush regions from this control
  const brushRegions = useMemo(
    () => regions.filter((r) => r.sourceControlName === controlConfig.name && r.type === 'brush'),
    [regions, controlConfig.name],
  )

  // Get image-space pointer coordinates
  const getImagePoint = useCallback((): { x: number; y: number } | null => {
    const p = zp.pointerToImage()
    if (!p) return null
    return p
  }, [zp])

  // Mouse handlers for brush drawing
  const onMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective) return
      if (e.evt.button !== 0) return
      const p = getImagePoint()
      if (!p) return
      if (hasLabels && !activeLabel) {
        getMessageInstance()?.warning('请先选择标签(点击或按数字键 1-9)')
        return
      }
      const ctx = maskCtxRef.current
      if (!ctx) return
      setIsDrawing(true)
      setHasUnsavedMask(true)
      drawBrushDot(ctx, p.x, p.y, brushSize)
      lastPointRef.current = { x: p.x, y: p.y }
      // Refresh Konva Image
      maskImageRef.current?.getLayer()?.batchDraw()
    },
    [readOnly, zp, getImagePoint, hasLabels, activeLabel, brushSize],
  )

  const onMouseMove = useCallback(() => {
    if (!isDrawing) return
    const p = getImagePoint()
    if (!p) return
    const ctx = maskCtxRef.current
    if (!ctx) return
    const last = lastPointRef.current
    if (last) {
      drawBrushLine(ctx, last.x, last.y, p.x, p.y, brushSize)
    } else {
      drawBrushDot(ctx, p.x, p.y, brushSize)
    }
    lastPointRef.current = { x: p.x, y: p.y }
    maskImageRef.current?.getLayer()?.batchDraw()
  }, [isDrawing, getImagePoint, brushSize])

  const onMouseUp = useCallback(() => {
    setIsDrawing(false)
    lastPointRef.current = null
  }, [])

  // Save current mask as a brush region
  const saveMask = useCallback(() => {
    const canvas = maskCanvasRef.current
    if (!canvas || !imageDimensions) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
    const rle = encodeRLE(imageData.data, canvas.width, canvas.height)

    if (!rle || rle === '0') {
      getMessageInstance()?.warning('画刷区域为空，请先在图像上绘制')
      return
    }

    onAddRegion({
      id: crypto.randomUUID(),
      type: 'brush',
      label: activeLabel ?? undefined,
      spatial: {
        x: 0,
        y: 0,
        width: imageDimensions.width,
        height: imageDimensions.height,
        rle,
        originalWidth: imageDimensions.width,
        originalHeight: imageDimensions.height,
      },
      sourceControlName: controlConfig.name,
      perRegionResults: {},
    })

    // Clear mask canvas for next brush region
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setHasUnsavedMask(false)
    maskImageRef.current?.getLayer()?.batchDraw()
  }, [imageDimensions, activeLabel, controlConfig.name, onAddRegion])

  // Clear current mask without saving
  const clearMask = useCallback(() => {
    const canvas = maskCanvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setHasUnsavedMask(false)
    maskImageRef.current?.getLayer()?.batchDraw()
  }, [])

  const handleDelete = useCallback(
    (id: string) => {
      onDeleteRegion(id)
    },
    [onDeleteRegion],
  )

  // Stable ref to avoid Ctrl+Z handler re-registration on every region change
  const brushRegionsRef = useRef(brushRegions)
  brushRegionsRef.current = brushRegions

  const handleUndo = useCallback(() => {
    const regs = brushRegionsRef.current
    const last = regs[regs.length - 1]
    if (last) {
      onDeleteRegion(last.id)
      onSelectRegion(null)
    }
  }, [onDeleteRegion, onSelectRegion])

  // Ctrl+Z
  useEffect(() => {
    if (readOnly) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        handleUndo()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [readOnly, handleUndo])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
      {!readOnly && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {hasLabels && (
            <LabelPalette
              labels={controlConfig.choices.map((c) => c.value)}
              activeLabel={activeLabel}
              onChange={setActiveLabel}
            />
          )}
          <Space.Compact>
            <Button icon={<FormatPainterOutlined />} onClick={saveMask} disabled={!hasUnsavedMask}>
              保存画刷
            </Button>
            <Button icon={<ClearOutlined />} onClick={clearMask} disabled={!hasUnsavedMask}>
              清除
            </Button>
          </Space.Compact>
          <Button icon={<UndoOutlined />} onClick={handleUndo} disabled={brushRegions.length === 0}>
            撤销区域
          </Button>
          <Button
            icon={<DeleteOutlined />}
            disabled={!selectedRegionId}
            onClick={() => selectedRegionId && onDeleteRegion(selectedRegionId)}
          >
            删除选中
          </Button>
          <Tag>{brushRegions.length} 个画刷区域</Tag>
        </div>
      )}
      {!readOnly && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
            笔刷大小:
          </Typography.Text>
          <Slider
            min={MIN_BRUSH_SIZE}
            max={MAX_BRUSH_SIZE}
            value={brushSize}
            onChange={setBrushSize}
            style={{ width: 120 }}
          />
          <Tag>{brushSize}px</Tag>
        </div>
      )}

      <div style={{ flex: 1, position: 'relative', minHeight: 400 }}>
        <ZoomPanImageStage
          controller={zp}
          toolbarExtra={null}
          onStageMouseDown={onMouseDown}
          onStageMouseMove={onMouseMove}
          onStageMouseUp={onMouseUp}
          renderContent={() => (
            <>
              {/* Render saved brush regions as semi-transparent overlays */}
              {brushRegions.map((region, i) => {
                // Brush regions cover the full image; they're rendered as an overlay
                if (
                  !region.spatial.rle ||
                  !region.spatial.originalWidth ||
                  !region.spatial.originalHeight
                )
                  return null
                return (
                  <KonvaImage
                    key={region.id}
                    id={region.id}
                    x={0}
                    y={0}
                    width={region.spatial.originalWidth}
                    height={region.spatial.originalHeight}
                    image={undefined}
                    opacity={0.4}
                    fill={labelColor(i)}
                    listening={false}
                  />
                )
              })}
              {/* Render live mask canvas as a Konva Image */}
              {!readOnly && maskCanvasRef.current && (
                <KonvaImage
                  ref={maskImageRef}
                  x={0}
                  y={0}
                  width={imageDimensions?.width ?? 0}
                  height={imageDimensions?.height ?? 0}
                  image={maskCanvasRef.current}
                  opacity={0.5}
                  listening={false}
                />
              )}
            </>
          )}
        />
      </div>
      {/* Region list — placed below canvas to avoid occluding the image */}
      {brushRegions.length > 0 && (
        <div
          style={{
            maxHeight: 120,
            overflowY: 'auto',
            background: 'var(--ant-color-bg-container)',
            border: '1px solid var(--ant-color-border)',
            borderRadius: 6,
            flexShrink: 0,
          }}
        >
          <List
            size="small"
            dataSource={brushRegions}
            renderItem={(region: AnnotationRegion, i: number) => (
              <List.Item
                style={{
                  padding: '4px 12px',
                  cursor: 'pointer',
                  background:
                    selectedRegionId === region.id ? 'var(--ant-color-primary-bg)' : undefined,
                }}
                onClick={() => onSelectRegion(region.id)}
              >
                <Space>
                  <Tag color={labelColor(i)}>{i + 1}</Tag>
                  <span>{region.label || `画刷 ${i + 1}`}</span>
                </Space>
                {!readOnly && (
                  <Button
                    type="text"
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(region.id)
                    }}
                  />
                )}
              </List.Item>
            )}
          />
        </div>
      )}
      {!readOnly && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          在图像上按住鼠标拖动画刷。完成后点击「保存画刷」。多个区域可叠加。
        </Typography.Text>
      )}
    </div>
  )
}
