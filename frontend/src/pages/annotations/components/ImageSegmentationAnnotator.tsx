import { useState, useRef, useEffect, useCallback } from 'react'
import { Button, Space, Select, List, Tag, Popconfirm } from 'antd'
import { DeleteOutlined, BorderOutlined, SelectOutlined } from '@ant-design/icons'
import { Stage, Layer, Image as KonvaImage, Line } from 'react-konva'
import type Konva from 'konva'
import type { AnnotationTask, AnnotationProjectDetail } from '@/types/annotation'
import type { AnnotationResultItem } from '@/types/annotation'
import { getMessageInstance } from '@/utils/messageHolder'

interface Polygon {
  id: string
  points: number[]
  label: string
  closed: boolean
}

interface ImageSegmentationAnnotatorProps {
  task: AnnotationTask
  project: AnnotationProjectDetail
  labels: string[]
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
}

type ToolMode = 'select' | 'draw'

export default function ImageSegmentationAnnotator({
  task,
  labels,
  onSubmit,
  submitting,
}: ImageSegmentationAnnotatorProps) {
  const imageUrl = task.data?.image as string | undefined
  const [image, setImage] = useState<HTMLImageElement | null>(null)
  const [polygons, setPolygons] = useState<Polygon[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [toolMode, setToolMode] = useState<ToolMode>('draw')
  const [currentPoints, setCurrentPoints] = useState<number[]>([])
  const [pendingLabelPoints, setPendingLabelPoints] = useState<number[] | null>(null)
  const stageRef = useRef<Konva.Stage>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [stageSize, setStageSize] = useState({ width: 600, height: 400 })

  useEffect(() => {
    setPolygons([])
    setSelectedId(null)
    setToolMode('draw')
    setCurrentPoints([])
    setPendingLabelPoints(null)
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

  const scale = image ? Math.min(stageSize.width / image.width, stageSize.height / image.height) : 1
  const offsetX = image ? (stageSize.width - image.width * scale) / 2 : 0
  const offsetY = image ? (stageSize.height - image.height * scale) / 2 : 0

  const handleStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (toolMode !== 'draw') return
      const stage = e.target.getStage()
      if (!stage) return
      const pos = stage.getPointerPosition()
      if (!pos) return
      setCurrentPoints((prev) => [...prev, pos.x, pos.y])
    },
    [toolMode],
  )

  const handleDoubleClick = useCallback(() => {
    if (currentPoints.length < 6) return
    if (labels.length === 1) {
      setPolygons((prev) => [
        ...prev,
        { id: crypto.randomUUID(), points: [...currentPoints], label: labels[0], closed: true },
      ])
    } else {
      setPendingLabelPoints([...currentPoints])
    }
    setCurrentPoints([])
  }, [currentPoints, labels])

  const handleLabelSelect = (label: string) => {
    if (!pendingLabelPoints) return
    setPolygons((prev) => [
      ...prev,
      { id: crypto.randomUUID(), points: [...pendingLabelPoints], label, closed: true },
    ])
    setPendingLabelPoints(null)
  }

  const handleDelete = (id: string) => {
    setPolygons((prev) => prev.filter((p) => p.id !== id))
    if (selectedId === id) setSelectedId(null)
  }

  const handleUndoPoint = () => {
    setCurrentPoints((prev) => prev.slice(0, -2))
  }

  const handleSubmit = () => {
    if (polygons.length === 0) {
      getMessageInstance()?.warning('请至少绘制一个标注区域')
      return
    }
    const imgW = image?.width || 1
    const imgH = image?.height || 1

    const result: AnnotationResultItem[] = polygons.map((poly) => {
      const points: number[][] = []
      for (let i = 0; i < poly.points.length; i += 2) {
        points.push([
          ((poly.points[i] - offsetX) / scale / imgW) * 100,
          ((poly.points[i + 1] - offsetY) / scale / imgH) * 100,
        ])
      }
      return {
        from_name: 'label',
        to_name: 'image',
        type: 'polygonlabels',
        value: { points, polygonlabels: [poly.label] },
      }
    })
    onSubmit(result)
  }

  const COLORS = ['#1677FF', '#52C41A', '#FAAD14', '#FF4D4F', '#722ED1', '#13C2C2', '#EB2F96']

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
      <Space>
        <Button
          type={toolMode === 'draw' ? 'primary' : 'default'}
          icon={<BorderOutlined />}
          onClick={() => {
            setToolMode('draw')
            setCurrentPoints([])
            setSelectedId(null)
          }}
        >
          绘制多边形
        </Button>
        <Button
          type={toolMode === 'select' ? 'primary' : 'default'}
          icon={<SelectOutlined />}
          onClick={() => {
            setToolMode('select')
            setCurrentPoints([])
          }}
        >
          选择
        </Button>
        {toolMode === 'draw' && currentPoints.length > 0 && (
          <Button onClick={handleUndoPoint}>撤销顶点</Button>
        )}
        <Popconfirm
          title="确认删除?"
          onConfirm={() => selectedId && handleDelete(selectedId)}
          disabled={!selectedId}
        >
          <Button icon={<DeleteOutlined />} disabled={!selectedId}>
            删除选中
          </Button>
        </Popconfirm>
        <Button
          type="primary"
          onClick={handleSubmit}
          disabled={submitting || polygons.length === 0}
        >
          {submitting ? '提交中...' : `提交 (${polygons.length})`}
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
          onClick={handleStageClick}
          onDblClick={handleDoubleClick}
        >
          <Layer>
            {image && (
              <KonvaImage image={image} x={offsetX} y={offsetY} scaleX={scale} scaleY={scale} />
            )}
            {polygons.map((poly, i) => (
              <Line
                key={poly.id}
                points={poly.points}
                closed={poly.closed}
                fill={`${COLORS[i % COLORS.length]}30`}
                stroke={COLORS[i % COLORS.length]}
                strokeWidth={2}
                onClick={() => {
                  if (toolMode === 'select') setSelectedId(poly.id)
                }}
              />
            ))}
            {currentPoints.length > 0 && (
              <Line points={currentPoints} stroke="#1677FF" strokeWidth={2} dash={[4, 4]} />
            )}
          </Layer>
        </Stage>
      </div>

      {toolMode === 'draw' && currentPoints.length > 0 && (
        <div style={{ padding: 4, color: 'var(--ant-color-text-secondary)', fontSize: 12 }}>
          点击添加顶点，双击闭合多边形。已有 {currentPoints.length / 2} 个顶点。
        </div>
      )}

      {pendingLabelPoints && (
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

      {polygons.length > 0 && (
        <List
          size="small"
          dataSource={polygons}
          style={{ maxHeight: 150, overflowY: 'auto' }}
          renderItem={(poly, i) => (
            <List.Item
              style={{ padding: '4px 12px', cursor: 'pointer' }}
              onClick={() => setSelectedId(poly.id)}
            >
              <Space>
                <Tag color={COLORS[i % COLORS.length]}>{i + 1}</Tag>
                <span>{poly.label}</span>
              </Space>
              <Button
                type="text"
                size="small"
                icon={<DeleteOutlined />}
                onClick={(e) => {
                  e.stopPropagation()
                  handleDelete(poly.id)
                }}
              />
            </List.Item>
          )}
        />
      )}
    </div>
  )
}
