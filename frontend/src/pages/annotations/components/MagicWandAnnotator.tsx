import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Slider, Space, Tag, Typography } from 'antd'
import { DeleteOutlined, ThunderboltOutlined } from '@ant-design/icons'
import { Image as KonvaImage } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import { labelColor } from './annotationColors'
import type { Region } from '../hooks/useAnnotationRegions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'
import { regionsOf } from '../utils/regions'
import { decodeRLE, encodeRLE } from '../utils/rleEncoder'
import { floodFill, maskToRgba } from '../utils/floodFill'

const DEFAULT_THRESHOLD = 15

function rleToHtmlImage(rle: string, width: number, height: number): HTMLImageElement {
  const imageData = decodeRLE(rle, width, height)
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  canvas.getContext('2d')!.putImageData(imageData, 0, 0)
  const img = new window.Image()
  img.src = canvas.toDataURL()
  return img
}

/**
 * MagicWand 标注器 —— 点击图像选种子点，flood-fill（颜色容差阈值）生成连通掩码，
 * 编码为 RLE（复用 Brush 契约）。拖动阈值滑块调整容差。需图像 CORS（useZoomPan 已设）。
 */
export default function MagicWandAnnotator({
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
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined
  const zp = useZoomPan(imageUrl)

  const [threshold, setThreshold] = useState(DEFAULT_THRESHOLD)
  const imageDataRef = useRef<ImageData | null>(null)
  const rleImageCache = useRef<Map<string, HTMLImageElement>>(new Map())

  useEffect(() => {
    const cache = rleImageCache.current
    return () => {
      cache.clear()
    }
  }, [])

  // 图像加载后读取像素数据（flood-fill 需像素访问；依赖 CORS）
  useEffect(() => {
    if (!zp.image) {
      imageDataRef.current = null
      return
    }
    const w = zp.image.width
    const h = zp.image.height
    if (!imageDimensions) onImageDimensionsChange({ width: w, height: h })
    try {
      const canvas = document.createElement('canvas')
      canvas.width = w
      canvas.height = h
      const ctx = canvas.getContext('2d', { willReadFrequently: true })!
      ctx.drawImage(zp.image, 0, 0)
      imageDataRef.current = ctx.getImageData(0, 0, w, h)
    } catch {
      imageDataRef.current = null
      getMessageInstance()?.error('无法读取图像像素（可能跨域），魔棒不可用')
    }
  }, [zp.image, imageDimensions, onImageDimensionsChange])

  const mwRegions = useMemo(
    () => regionsOf(regions, controlConfig.name, 'magicwand'),
    [regions, controlConfig.name],
  )

  const getRleImage = useCallback((rle: string, w: number, h: number): HTMLImageElement => {
    const key = `${rle.slice(0, 50)}-${w}-${h}`
    const cached = rleImageCache.current.get(key)
    if (cached) return cached
    const img = rleToHtmlImage(rle, w, h)
    rleImageCache.current.set(key, img)
    return img
  }, [])

  const onStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective || e.evt.button !== 0) return
      const imgData = imageDataRef.current
      if (!imgData) {
        getMessageInstance()?.warning('图像像素未就绪')
        return
      }
      const p = zp.pointerToImage()
      if (!p) return
      const mask = floodFill(imgData, Math.round(p.x), Math.round(p.y), threshold)
      const rle = encodeRLE(
        maskToRgba(mask, imgData.width, imgData.height),
        imgData.width,
        imgData.height,
      )
      if (!rle || rle === '0') {
        getMessageInstance()?.warning('该区域为空，尝试调整阈值')
        return
      }
      onAddRegion({
        id: crypto.randomUUID(),
        fromName: controlConfig.name,
        value: {
          kind: 'magicwand',
          rle,
          originalWidth: imgData.width,
          originalHeight: imgData.height,
        },
        perRegionResults: {},
      })
    },
    [readOnly, zp, threshold, controlConfig.name, onAddRegion],
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
      {!readOnly && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Button type="primary" icon={<ThunderboltOutlined />} disabled>
            魔棒模式
          </Button>
          <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
            颜色容差:
          </Typography.Text>
          <Slider
            min={1}
            max={80}
            value={threshold}
            onChange={setThreshold}
            style={{ width: 140 }}
          />
          <Tag>{threshold}</Tag>
          <Button
            icon={<DeleteOutlined />}
            disabled={!selectedRegionId}
            onClick={() => selectedRegionId && onDeleteRegion(selectedRegionId)}
          >
            删除选中
          </Button>
          <Tag>{mwRegions.length} 个区域</Tag>
        </div>
      )}

      <div style={{ flex: 1, position: 'relative', minHeight: 400 }}>
        <ZoomPanImageStage
          controller={zp}
          toolbarExtra={null}
          onStageClick={onStageClick}
          renderContent={() => (
            <>
              {mwRegions.map((region) => (
                <KonvaImage
                  key={region.id}
                  id={region.id}
                  x={0}
                  y={0}
                  width={region.value.originalWidth}
                  height={region.value.originalHeight}
                  image={getRleImage(
                    region.value.rle,
                    region.value.originalWidth,
                    region.value.originalHeight,
                  )}
                  opacity={0.4}
                  listening={false}
                  onClick={() =>
                    !readOnly && onSelectRegion(selectedRegionId === region.id ? null : region.id)
                  }
                />
              ))}
            </>
          )}
        />
      </div>

      {mwRegions.length > 0 && (
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
            dataSource={mwRegions}
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
                  <span>魔棒区域 {i + 1}</span>
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
          点击图像中的目标区域，魔棒按颜色容差自动选中连通区域。调整阈值改变选取范围。
        </Typography.Text>
      )}
    </div>
  )
}
