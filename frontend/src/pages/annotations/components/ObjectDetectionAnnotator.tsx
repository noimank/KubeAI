import { useState, useRef, useEffect, useCallback } from 'react'
import { Button, Space, Select, List, Tag, Popconfirm } from 'antd'
import { DeleteOutlined, DragOutlined, SelectOutlined } from '@ant-design/icons'
import { Stage, Layer, Image as KonvaImage, Rect, Transformer } from 'react-konva'
import type Konva from 'konva'
import type { AnnotationTask, AnnotationProjectDetail } from '@/types/annotation'
import type { AnnotationResultItem } from '@/types/annotation'
import { getMessageInstance } from '@/utils/messageHolder'

interface BBox {
  id: string
  x: number
  y: number
  width: number
  height: number
  label: string
}

interface ObjectDetectionAnnotatorProps {
  task: AnnotationTask
  project: AnnotationProjectDetail
  labels: string[]
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
}

type ToolMode = 'select' | 'draw'

export default function ObjectDetectionAnnotator({
  task,
  labels,
  onSubmit,
  submitting,
}: ObjectDetectionAnnotatorProps) {
  const imageUrl = task.data?.image as string | undefined
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [bboxes, setBboxes] = useState<BBox[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [toolMode, setToolMode] = useState<ToolMode>('draw')
  const [drawingBbox, setDrawingBbox] = useState<{
    x: number
    y: number
    w: number
    h: number
  } | null>(null)
  const [pendingLabelBbox, setPendingLabelBbox] = useState<{
    x: number
    y: number
    w: number
    h: number
  } | null>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const transformerRef = useRef<Konva.Transformer>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [stageSize, setStageSize] = useState({ width: 600, height: 400 })

  useEffect(() => {
    setBboxes([])
    setSelectedId(null)
    setToolMode('draw')
    setDrawingBbox(null)
    setPendingLabelBbox(null)
    setImage(null)
  }, [task.id])

  useEffect(() => {
    if (!imageUrl) return
    let cancelled = false
    const img = new window.Image()
    img.crossOrigin = 'anonymous'
    img.src = imageUrl
    img.onload = () => {
      if (!cancelled) setImage(img)
    }
    return () => {
      cancelled = true
    }
  }, [imageUrl])

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setStageSize({
          width: entry.contentRect.width,
          height: Math.max(400, entry.contentRect.height),
        })
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    const transformer = transformerRef.current
    const stage = stageRef.current
    if (!transformer || !stage) return
    const node = selectedId ? stage.findOne(`#${selectedId}`) : null
    transformer.nodes(node ? [node] : [])
    transformer.getLayer()?.batchDraw()
  }, [selectedId, bboxes])

  const scale = image ? Math.min(stageSize.width / image.width, stageSize.height / image.height) : 1
  const offsetX = image ? (stageSize.width - image.width * scale) / 2 : 0
  const offsetY = image ? (stageSize.height - image.height * scale) / 2 : 0

  const handleMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (toolMode !== 'draw') return
      const stage = e.target.getStage()
      if (!stage) return
      const pos = stage.getPointerPosition()
      if (!pos) return
      setDrawingBbox({ x: pos.x, y: pos.y, w: 0, h: 0 })
    },
    [toolMode],
  )

  const handleMouseMove = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (!drawingBbox) return
      const stage = e.target.getStage()
      if (!stage) return
      const pos = stage.getPointerPosition()
      if (!pos) return
      setDrawingBbox((prev) => (prev ? { ...prev, w: pos.x - prev.x, h: pos.y - prev.y } : null))
    },
    [drawingBbox],
  )

  const handleMouseUp = useCallback(() => {
    if (!drawingBbox) return
    const { x, y, w, h } = drawingBbox
    setDrawingBbox(null)
    if (Math.abs(w) < 5 || Math.abs(h) < 5) return
    const nx = w < 0 ? x + w : x
    const ny = h < 0 ? y + h : y
    const nw = Math.abs(w)
    const nh = Math.abs(h)
    if (labels.length === 1) {
      setBboxes((prev) => [
        ...prev,
        { id: crypto.randomUUID(), x: nx, y: ny, width: nw, height: nh, label: labels[0] },
      ])
    } else {
      setPendingLabelBbox({ x: nx, y: ny, w: nw, h: nh })
    }
  }, [drawingBbox, labels])

  const handleLabelSelect = (label: string) => {
    if (!pendingLabelBbox) return
    setBboxes((prev) => [
      ...prev,
      {
        id: crypto.randomUUID(),
        x: pendingLabelBbox.x,
        y: pendingLabelBbox.y,
        width: pendingLabelBbox.w,
        height: pendingLabelBbox.h,
        label,
      },
    ])
    setPendingLabelBbox(null)
  }

  const handleDelete = (id: string) => {
    setBboxes((prev) => prev.filter((b) => b.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  const handleSubmit = () => {
    if (bboxes.length === 0) {
      getMessageInstance()?.warning('请至少绘制一个标注框')
      return
    }
    const imgW = image?.width || 1
    const imgH = image?.height || 1

    const result: AnnotationResultItem[] = bboxes.map((bbox) => ({
      from_name: 'label',
      to_name: 'image',
      type: 'rectanglelabels',
      value: {
        x: ((bbox.x - offsetX) / scale / imgW) * 100,
        y: ((bbox.y - offsetY) / scale / imgH) * 100,
        width: (bbox.width / scale / imgW) * 100,
        height: (bbox.height / scale / imgH) * 100,
        rectanglelabels: [bbox.label],
      },
    }))
    onSubmit(result)
  }

  const COLORS = ['#1677FF', '#52C41A', '#FAAD14', '#FF4D4F', '#722ED1', '#13C2C2', '#EB2F96']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
      <Space>
        <Button
          type={toolMode === 'draw' ? 'primary' : 'default'}
          icon={<DragOutlined />}
          onClick={() => {
            setToolMode('draw')
            setSelectedId(null)
          }}
        >
          绘制矩形
        </Button>
        <Button
          type={toolMode === 'select' ? 'primary' : 'default'}
          icon={<SelectOutlined />}
          onClick={() => setToolMode('select')}
        >
          选择/移动
        </Button>
        <Popconfirm
          title="确认删除?"
          onConfirm={() => selectedId && handleDelete(selectedId)}
          disabled={!selectedId}
        >
          <Button icon={<DeleteOutlined />} disabled={!selectedId}>
            删除选中
          </Button>
        </Popconfirm>
        <Button type="primary" onClick={handleSubmit} disabled={submitting || bboxes.length === 0}>
          {submitting ? '提交中...' : `提交 (${bboxes.length})`}
        </Button>
      </Space>

      <div
        ref={containerRef}
        style={{
          flex: 1,
          border: '1px solid var(--ant-color-border)',
          borderRadius: 6,
          overflow: 'hidden',
        }}
      >
        <Stage
          ref={stageRef}
          width={stageSize.width}
          height={stageSize.height}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
        >
          <Layer>
            {image && (
              <KonvaImage image={image} x={offsetX} y={offsetY} scaleX={scale} scaleY={scale} />
            )}
            {bboxes.map((bbox, i) => (
              <Rect
                key={bbox.id}
                id={bbox.id}
                x={bbox.x}
                y={bbox.y}
                width={bbox.width}
                height={bbox.height}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                fill={`${COLORS[i % COLORS.length]}20`}
                draggable={toolMode === 'select'}
                onClick={() => {
                  if (toolMode === 'select') setSelectedId(bbox.id)
                }}
                onTap={() => {
                  if (toolMode === 'select') setSelectedId(bbox.id)
                }}
                onDragEnd={(e) => {
                  setBboxes((prev) =>
                    prev.map((b) =>
                      b.id === bbox.id ? { ...b, x: e.target.x(), y: e.target.y() } : b,
                    ),
                  )
                }}
                onTransformEnd={(e) => {
                  const node = e.target
                  setBboxes((prev) =>
                    prev.map((b) =>
                      b.id === bbox.id
                        ? {
                            ...b,
                            x: node.x(),
                            y: node.y(),
                            width: Math.max(5, node.width() * node.scaleX()),
                            height: Math.max(5, node.height() * node.scaleY()),
                          }
                        : b,
                    ),
                  )
                  node.scaleX(1)
                  node.scaleY(1)
                }}
              />
            ))}
            {drawingBbox && (
              <Rect
                x={drawingBbox.w < 0 ? drawingBbox.x + drawingBbox.w : drawingBbox.x}
                y={drawingBbox.h < 0 ? drawingBbox.y + drawingBbox.h : drawingBbox.y}
                width={Math.abs(drawingBbox.w)}
                height={Math.abs(drawingBbox.h)}
                stroke="#1677FF"
                strokeWidth={2}
                dash={[4, 4]}
              />
            )}
            {selectedId && (
              <Transformer
                ref={transformerRef}
                boundBoxFunc={(_oldBox, newBox) => {
                  if (newBox.width < 5 || newBox.height < 5) return _oldBox
                  return newBox
                }}
              />
            )}
          </Layer>
        </Stage>
      </div>

      {pendingLabelBbox && (
        <div style={{ padding: 8, background: 'var(--ant-color-bg-layout)', borderRadius: 6 }}>
          <span style={{ marginRight: 8 }}>选择标签:</span>
          <Select
            placeholder="选择标签"
            style={{ width: 200 }}
            onSelect={handleLabelSelect}
            autoFocus
            options={labels.map((l) => ({ label: l, value: l }))}
          />
        </div>
      )}

      {bboxes.length > 0 && (
        <List
          size="small"
          dataSource={bboxes}
          style={{ maxHeight: 150, overflowY: 'auto' }}
          renderItem={(bbox, i) => (
            <List.Item
              style={{ padding: '4px 12px', cursor: 'pointer' }}
              onClick={() => setSelectedId(bbox.id)}
            >
              <Space>
                <Tag color={COLORS[i % COLORS.length]}>{i + 1}</Tag>
                <span>{bbox.label}</span>
              </Space>
              <Button
                type="text"
                size="small"
                icon={<DeleteOutlined />}
                onClick={(e) => {
                  e.stopPropagation()
                  handleDelete(bbox.id)
                }}
              />
            </List.Item>
          )}
        />
      )}
    </div>
  )
}
