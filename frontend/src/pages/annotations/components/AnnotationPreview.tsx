import { useEffect, useMemo, useRef, useState } from 'react'
import { Card, Image, Rate, Space, Tag, Typography } from 'antd'
import { Stage, Layer, Image as KonvaImage, Rect, Line, Ellipse, Circle } from 'react-konva'
import type { AnnotationResultItem } from '@/types/annotation'

interface AnnotationPreviewProps {
  task: { data?: Record<string, unknown> }
  result: AnnotationResultItem[] | null | undefined
  annotationPayload?: Record<string, unknown> | null
}

const COLORS = ['#1890FF', '#52C41A', '#FAAD14', '#FF4D4F', '#722ED1', '#13C2C2', '#EB2F96']

const { Text } = Typography

interface Entry {
  index: number
  item: AnnotationResultItem
  color: string
  labels: string[]
}

function getImageField(data: Record<string, unknown> | undefined): string | undefined {
  if (!data) return undefined
  for (const [key, value] of Object.entries(data)) {
    if (key.startsWith('kubeai')) continue
    if (typeof value === 'string' && /^\/(api|storage)/.test(value)) return key
  }
  return undefined
}

function getTextField(data: Record<string, unknown> | undefined): string | undefined {
  if (!data) return undefined
  for (const [key, value] of Object.entries(data)) {
    if (key.startsWith('kubeai')) continue
    if (typeof value === 'string' && value && !/^(\/|https?:\/\/)/.test(value)) return key
  }
  return undefined
}

function pickLabels(item: AnnotationResultItem): string[] {
  const v = item.value as Record<string, unknown>
  for (const key of [
    'rectanglelabels',
    'polygonlabels',
    'brushlabels',
    'keypointlabels',
    'ellipselabels',
    'labels',
    'choices',
  ]) {
    const arr = v[key]
    if (Array.isArray(arr) && arr.every((x) => typeof x === 'string')) return arr as string[]
  }
  return []
}

function useImage(url: string | undefined) {
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  useEffect(() => {
    if (!url) {
      setImage(null)
      return
    }
    let cancelled = false
    const img = new window.Image()
    img.crossOrigin = 'anonymous'
    img.src = url
    img.onload = () => {
      if (!cancelled) setImage(img)
    }
    img.onerror = () => {
      if (!cancelled) setImage(null)
    }
    return () => {
      cancelled = true
    }
  }, [url])
  return image
}

function EntryHead({ entry }: { entry: Entry }) {
  if (entry.labels.length === 0) return null
  return (
    <Space wrap>
      {entry.labels.map((label, j) => (
        <Tag key={j} color={entry.color} style={{ marginInlineEnd: 0 }}>
          {label}
        </Tag>
      ))}
    </Space>
  )
}

function AnnotationSourceFile({ payload }: { payload: Record<string, unknown> }) {
  return (
    <details style={{ marginTop: 12 }}>
      <summary
        style={{ cursor: 'pointer', color: 'var(--ant-color-text-secondary)', fontSize: 12 }}
      >
        查看标注文件原文（与磁盘一致）
      </summary>
      <pre
        style={{
          maxHeight: 360,
          overflow: 'auto',
          margin: '8px 0 0',
          fontSize: 12,
          background: 'var(--ant-color-bg-layout)',
          padding: 8,
          borderRadius: 4,
        }}
      >
        {JSON.stringify(payload, null, 2)}
      </pre>
    </details>
  )
}

function ImageOverlay({ imageUrl, entries }: { imageUrl: string; entries: Entry[] }) {
  const image = useImage(imageUrl)
  const containerRef = useRef<HTMLDivElement>(null)
  const [stageSize, setStageSize] = useState({ width: 600, height: 400 })

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((rs) => {
      for (const r of rs) {
        setStageSize({
          width: r.contentRect.width,
          height: Math.max(360, r.contentRect.height),
        })
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  const scale = image ? Math.min(stageSize.width / image.width, stageSize.height / image.height) : 1
  const offsetX = image ? (stageSize.width - image.width * scale) / 2 : 0
  const offsetY = image ? (stageSize.height - image.height * scale) / 2 : 0

  if (!image) {
    return (
      <div style={{ textAlign: 'center', padding: 24 }}>
        <Image src={imageUrl} style={{ maxHeight: 360 }} />
      </div>
    )
  }

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: 460,
        border: '1px solid var(--ant-color-border)',
        borderRadius: 6,
        overflow: 'hidden',
        background: 'var(--ant-color-bg-container)',
      }}
    >
      <Stage width={stageSize.width} height={stageSize.height}>
        <Layer>
          <KonvaImage image={image} x={offsetX} y={offsetY} scaleX={scale} scaleY={scale} />
          {entries.map((entry) => {
            const v = entry.item.value as Record<string, unknown>
            const color = entry.color
            if (entry.item.type === 'rectanglelabels' || entry.item.type === 'rectangle') {
              const x = (Number(v.x) / 100) * image.width * scale + offsetX
              const y = (Number(v.y) / 100) * image.height * scale + offsetY
              const w = (Number(v.width) / 100) * image.width * scale
              const h = (Number(v.height) / 100) * image.height * scale
              return (
                <Rect
                  key={entry.index}
                  x={x}
                  y={y}
                  width={w}
                  height={h}
                  stroke={color}
                  strokeWidth={2}
                  fill={`${color}20`}
                />
              )
            }
            if (entry.item.type === 'polygonlabels' || entry.item.type === 'polygon') {
              const points = (Array.isArray(v.points) ? v.points : [])
                .filter((p): p is number[] => Array.isArray(p) && p.length >= 2)
                .flatMap((p) => [
                  (p[0] / 100) * image.width * scale + offsetX,
                  (p[1] / 100) * image.height * scale + offsetY,
                ])
              return (
                <Line
                  key={entry.index}
                  points={points}
                  closed
                  stroke={color}
                  strokeWidth={2}
                  fill={`${color}30`}
                />
              )
            }
            if (entry.item.type === 'keypointlabels' || entry.item.type === 'keypoint') {
              const kpX = (Number(v.x) / 100) * image.width * scale + offsetX
              const kpY = (Number(v.y) / 100) * image.height * scale + offsetY
              return (
                <Circle
                  key={entry.index}
                  x={kpX}
                  y={kpY}
                  radius={6}
                  fill={color}
                  stroke="#fff"
                  strokeWidth={2}
                />
              )
            }
            if (entry.item.type === 'ellipselabels' || entry.item.type === 'ellipse') {
              const cx = (Number(v.x) / 100) * image.width * scale + offsetX
              const cy = (Number(v.y) / 100) * image.height * scale + offsetY
              const rx = (Number(v.radiusX || Number(v.width) / 2) / 100) * image.width * scale
              const ry = (Number(v.radiusY || Number(v.height) / 2) / 100) * image.height * scale
              return (
                <Ellipse
                  key={entry.index}
                  x={cx}
                  y={cy}
                  radiusX={rx}
                  radiusY={ry}
                  stroke={color}
                  strokeWidth={2}
                  fill={`${color}20`}
                  rotation={Number(v.rotation) || 0}
                />
              )
            }
            return null
          })}
        </Layer>
      </Stage>
    </div>
  )
}

function imageEntries(entries: Entry[]): Entry[] {
  return entries.filter((e) =>
    [
      'rectanglelabels',
      'rectangle',
      'polygonlabels',
      'polygon',
      'keypointlabels',
      'keypoint',
      'ellipselabels',
      'ellipse',
    ].includes(e.item.type),
  )
}

function shapeListGroups(entries: Entry[]) {
  return entries.filter((e) =>
    [
      'rectanglelabels',
      'rectangle',
      'polygonlabels',
      'polygon',
      'brushlabels',
      'keypointlabels',
      'labels',
    ].includes(e.item.type),
  )
}

function choicesEntries(entries: Entry[]): Entry[] {
  return entries.filter((e) => e.item.type === 'choices')
}

function textareaEntries(entries: Entry[]): Entry[] {
  return entries.filter((e) => e.item.type === 'textarea')
}

/** 检查是否有 perRegion textarea（即 textarea 带有 area id） */
function hasPerRegionTextareas(entries: Entry[]): boolean {
  return entries.some((e) => e.item.type === 'textarea' && !!e.item.id)
}

function ratingEntries(entries: Entry[]): Entry[] {
  return entries.filter((e) => e.item.type === 'rating')
}

function numberEntries(entries: Entry[]): Entry[] {
  return entries.filter((e) => e.item.type === 'number')
}

function taxonomyEntries(entries: Entry[]): Entry[] {
  return entries.filter((e) => e.item.type === 'taxonomy')
}

export default function AnnotationPreview({
  task,
  result,
  annotationPayload,
}: AnnotationPreviewProps) {
  const entries: Entry[] = useMemo(() => {
    if (!result || result.length === 0) return []
    return result.map((item, i) => ({
      index: i,
      item,
      color: COLORS[i % COLORS.length],
      labels: pickLabels(item),
    }))
  }, [result])

  const imageField = getImageField(task.data)
  const textField = getTextField(task.data)
  const imageUrl =
    imageField && typeof task.data?.[imageField] === 'string'
      ? (task.data[imageField] as string)
      : undefined
  const textContent =
    textField && typeof task.data?.[textField] === 'string'
      ? (task.data[textField] as string)
      : undefined

  const hasResult = entries.length > 0
  const overlays = imageEntries(entries)
  const shapes = shapeListGroups(entries)
  const choices = choicesEntries(entries)
  const textareas = textareaEntries(entries)
  const ratings = ratingEntries(entries)
  const numbers = numberEntries(entries)
  const taxonomies = taxonomyEntries(entries)

  if (!hasResult) {
    return (
      <div>
        {imageUrl && (
          <div style={{ textAlign: 'center', marginBottom: 12 }}>
            <Image src={imageUrl} style={{ maxHeight: 360 }} />
          </div>
        )}
        {textContent && (
          <Card size="small" title="文本内容" style={{ marginBottom: 12 }}>
            <Text style={{ whiteSpace: 'pre-wrap' }}>{textContent}</Text>
          </Card>
        )}
        {!imageUrl && !textContent && <Text type="secondary">尚未提交标注结果</Text>}
      </div>
    )
  }

  return (
    <div>
      {imageUrl &&
        (overlays.length > 0 ? (
          <ImageOverlay imageUrl={imageUrl} entries={overlays} />
        ) : (
          <div style={{ textAlign: 'center', marginBottom: 12 }}>
            <Image src={imageUrl} style={{ maxHeight: 360 }} />
          </div>
        ))}

      {textContent && textareas.length === 0 && (
        <Card size="small" title="文本内容" style={{ marginBottom: 12 }}>
          <Text style={{ whiteSpace: 'pre-wrap' }}>{textContent}</Text>
        </Card>
      )}

      {choices.length > 0 && (
        <Card size="small" title="分类结果" style={{ marginBottom: 12 }}>
          {choices.map((entry) => (
            <EntryHead key={entry.index} entry={entry} />
          ))}
        </Card>
      )}

      {shapes.length > 0 && (
        <Card size="small" title={`区域标注 (${shapes.length})`} style={{ marginBottom: 12 }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {shapes.map((entry) => {
              // perRegion 关联的 textarea
              const regionTextareas = hasPerRegionTextareas(entries)
                ? entries.filter((e) => e.item.type === 'textarea' && e.item.id === entry.item.id)
                : []
              return (
                <div key={entry.index}>
                  <EntryHead entry={entry} />
                  {regionTextareas.map((ta) => {
                    const tv = ta.item.value as Record<string, unknown>
                    return (
                      <Text
                        key={ta.index}
                        type="secondary"
                        style={{ fontSize: 12, display: 'block', marginLeft: 8 }}
                      >
                        📝 {String((tv.text as unknown[])?.[0] ?? '')}
                      </Text>
                    )
                  })}
                </div>
              )
            })}
          </Space>
        </Card>
      )}

      {!hasPerRegionTextareas(entries) && textareas.length > 0 && (
        <Card size="small" title="文本标注" style={{ marginBottom: 12 }}>
          {textareas.map((entry) => {
            const v = entry.item.value as Record<string, unknown>
            return (
              <div key={entry.index}>
                <Text style={{ whiteSpace: 'pre-wrap' }}>{String(v.text ?? '')}</Text>
              </div>
            )
          })}
        </Card>
      )}

      {ratings.length > 0 && (
        <Card size="small" title="评分" style={{ marginBottom: 12 }}>
          {ratings.map((entry) => {
            const v = entry.item.value as Record<string, unknown>
            const rating = Number(v.rating ?? 0)
            return (
              <div key={entry.index}>
                <Space>
                  <Rate
                    count={10}
                    value={rating}
                    allowHalf
                    disabled
                    style={{ color: entry.color, fontSize: 18 }}
                  />
                  <strong>{rating}/10</strong>
                </Space>
              </div>
            )
          })}
        </Card>
      )}

      {numbers.length > 0 && (
        <Card size="small" title="数值" style={{ marginBottom: 12 }}>
          {numbers.map((entry) => {
            const v = entry.item.value as Record<string, unknown>
            return (
              <div key={entry.index}>
                <Text strong style={{ fontSize: 18 }}>
                  {String(v.number ?? '-')}
                </Text>
              </div>
            )
          })}
        </Card>
      )}

      {taxonomies.length > 0 && (
        <Card size="small" title="分类树" style={{ marginBottom: 12 }}>
          {taxonomies.map((entry) => {
            const v = entry.item.value as Record<string, unknown>
            const paths = (v.taxonomy as unknown[]) ?? []
            return (
              <div key={entry.index}>
                <Space wrap>
                  {paths.map((p, i) => (
                    <Tag key={i} color={entry.color}>
                      {Array.isArray(p) ? p.join(' / ') : String(p)}
                    </Tag>
                  ))}
                </Space>
              </div>
            )
          })}
        </Card>
      )}

      {annotationPayload && <AnnotationSourceFile payload={annotationPayload} />}
    </div>
  )
}
