import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Segmented, Slider, Space, Tag, Typography } from 'antd'
import {
  ClearOutlined,
  DeleteOutlined,
  FormatPainterOutlined,
  SaveOutlined,
  ScissorOutlined,
  UndoOutlined,
} from '@ant-design/icons'
import { Image as KonvaImage } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import type { Region } from '../hooks/useAnnotationRegions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'
import { regionsOf } from '../utils/regions'

const DEFAULT_BRUSH_SIZE = 20
type DrawMode = 'draw' | 'erase'

function drawDot(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath()
  ctx.arc(x, y, r, 0, Math.PI * 2)
  ctx.fill()
}
function eraseDot(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.save()
  ctx.globalCompositeOperation = 'destination-out'
  ctx.beginPath()
  ctx.arc(x, y, r, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
}
function strokeLine(
  ctx: CanvasRenderingContext2D,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  r: number,
  fn: (ctx: CanvasRenderingContext2D, x: number, y: number, r: number) => void,
) {
  const dx = x1 - x0,
    dy = y1 - y0
  const dist = Math.sqrt(dx * dx + dy * dy)
  const step = r * 0.5
  if (dist < step) {
    fn(ctx, x1, y1, r)
    return
  }
  const steps = Math.ceil(dist / step)
  for (let i = 0; i <= steps; i++) fn(ctx, x0 + dx * (i / steps), y0 + dy * (i / steps), r)
}

/**
 * Bitmask / BitmaskLabels 标注器 —— 像素级掩码绘制（笔刷/橡皮），保存为 PNG dataURL。
 * 与 Brush 的差异：输出 imageDataURL（LS bitmask 契约）而非 RLE；渲染直接用 dataURL。
 */
export default function BitmaskAnnotator({
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
  const hasLabels = controlConfig.type === 'bitmasklabels'
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined
  const zp = useZoomPan(imageUrl)

  const [brushSize, setBrushSize] = useState(DEFAULT_BRUSH_SIZE)
  const [drawMode, setDrawMode] = useState<DrawMode>('draw')
  const [activeLabel, setActiveLabel] = useState<string | null>(
    hasLabels ? (controlConfig.choices[0]?.value ?? null) : null,
  )
  const [isDrawing, setIsDrawing] = useState(false)
  const [hasUnsavedMask, setHasUnsavedMask] = useState(false)

  const maskCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const maskCtxRef = useRef<CanvasRenderingContext2D | null>(null)
  const maskImageRef = useRef<Konva.Image | null>(null)
  const lastPointRef = useRef<{ x: number; y: number } | null>(null)
  const throttleRef = useRef(0)
  const dataURLImageCache = useRef<Map<string, HTMLImageElement>>(new Map())

  useEffect(() => {
    const cache = dataURLImageCache.current
    return () => {
      cache.clear()
    }
  }, [])

  useEffect(() => {
    setHasUnsavedMask(false)
    setDrawMode('draw')
    lastPointRef.current = null
    dataURLImageCache.current.clear()
    if (hasLabels) setActiveLabel(controlConfig.choices[0]?.value ?? null)
    if (maskCtxRef.current && maskCanvasRef.current) {
      maskCtxRef.current.clearRect(0, 0, maskCanvasRef.current.width, maskCanvasRef.current.height)
    }
  }, [task.id, hasLabels, controlConfig.choices])

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
        const ctx = canvas.getContext('2d')!
        ctx.fillStyle = 'rgba(0,0,0,1)'
        maskCtxRef.current = ctx
      }
    }
  }, [zp.image, imageDimensions, onImageDimensionsChange])

  const bitmaskRegions = useMemo(
    () => regionsOf(regions, controlConfig.name, 'bitmask'),
    [regions, controlConfig.name],
  )

  const getDataURLImage = useCallback((dataURL: string): HTMLImageElement => {
    const cached = dataURLImageCache.current.get(dataURL)
    if (cached) return cached
    const img = new window.Image()
    img.src = dataURL
    dataURLImageCache.current.set(dataURL, img)
    return img
  }, [])

  const onMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective || e.evt.button !== 0) return
      const p = zp.pointerToImage()
      if (!p || !maskCtxRef.current) return
      if (hasLabels && !activeLabel) {
        getMessageInstance()?.warning('请先选择标签')
        return
      }
      setIsDrawing(true)
      setHasUnsavedMask(true)
      const fn = drawMode === 'erase' ? eraseDot : drawDot
      fn(maskCtxRef.current, p.x, p.y, brushSize)
      lastPointRef.current = { x: p.x, y: p.y }
      maskImageRef.current?.getLayer()?.batchDraw()
    },
    [readOnly, zp, hasLabels, activeLabel, brushSize, drawMode],
  )

  const onMouseMove = useCallback(() => {
    if (!isDrawing) return
    const now = performance.now()
    if (now - throttleRef.current < 33) return
    throttleRef.current = now
    const p = zp.pointerToImage()
    if (!p || !maskCtxRef.current) return
    const fn = drawMode === 'erase' ? eraseDot : drawDot
    const last = lastPointRef.current
    if (last) strokeLine(maskCtxRef.current, last.x, last.y, p.x, p.y, brushSize, fn)
    else fn(maskCtxRef.current, p.x, p.y, brushSize)
    lastPointRef.current = { x: p.x, y: p.y }
    maskImageRef.current?.getLayer()?.batchDraw()
  }, [isDrawing, zp, brushSize, drawMode])

  const onMouseUp = useCallback(() => {
    setIsDrawing(false)
    lastPointRef.current = null
  }, [])

  const saveMask = useCallback(() => {
    const canvas = maskCanvasRef.current
    if (!canvas || !imageDimensions) return
    const dataURL = canvas.toDataURL('image/png')
    if (canvas.width * canvas.height < 1) {
      getMessageInstance()?.warning('掩码为空，请先绘制')
      return
    }
    onAddRegion({
      id: crypto.randomUUID(),
      fromName: controlConfig.name,
      label: activeLabel ?? undefined,
      value: {
        kind: 'bitmask',
        dataURL,
        originalWidth: imageDimensions.width,
        originalHeight: imageDimensions.height,
      },
      perRegionResults: {},
    })
    const ctx = canvas.getContext('2d')!
    ctx.clearRect(0, 0, canvas.width, canvas.height)
    setHasUnsavedMask(false)
    maskImageRef.current?.getLayer()?.batchDraw()
  }, [imageDimensions, activeLabel, controlConfig.name, onAddRegion])

  const clearMask = useCallback(() => {
    const canvas = maskCanvasRef.current
    if (!canvas) return
    canvas.getContext('2d')!.clearRect(0, 0, canvas.width, canvas.height)
    setHasUnsavedMask(false)
    maskImageRef.current?.getLayer()?.batchDraw()
  }, [])

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
          <Segmented
            size="small"
            value={drawMode}
            onChange={(v) => setDrawMode(v as DrawMode)}
            options={[
              { label: '绘制', value: 'draw', icon: <FormatPainterOutlined /> },
              { label: '擦除', value: 'erase', icon: <ScissorOutlined /> },
            ]}
          />
          <Button icon={<SaveOutlined />} onClick={saveMask} disabled={!hasUnsavedMask}>
            保存掩码
          </Button>
          <Button icon={<ClearOutlined />} onClick={clearMask} disabled={!hasUnsavedMask}>
            清除
          </Button>
          <Button
            icon={<UndoOutlined />}
            disabled={!selectedRegionId}
            onClick={() => selectedRegionId && onDeleteRegion(selectedRegionId)}
          >
            删除选中
          </Button>
          <Tag>{bitmaskRegions.length} 个掩码</Tag>
        </div>
      )}
      {!readOnly && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
            笔刷:
          </Typography.Text>
          <Slider
            min={2}
            max={80}
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
              {bitmaskRegions.map((region) => (
                <KonvaImage
                  key={region.id}
                  id={region.id}
                  x={0}
                  y={0}
                  width={region.value.originalWidth}
                  height={region.value.originalHeight}
                  image={getDataURLImage(region.value.dataURL)}
                  opacity={0.4}
                  listening={false}
                  onClick={() =>
                    !readOnly && onSelectRegion(selectedRegionId === region.id ? null : region.id)
                  }
                />
              ))}
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

      {bitmaskRegions.length > 0 && (
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
            dataSource={bitmaskRegions}
            renderItem={(region: Region, i: number) => (
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
                  <span>{region.label || `掩码 ${i + 1}`}</span>
                </Space>
                {!readOnly && (
                  <Button
                    type="text"
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      onDeleteRegion(region.id)
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
          在图像上拖动绘制像素掩码（黑=前景）。完成后点「保存掩码」。
        </Typography.Text>
      )}
    </div>
  )
}
