import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Popconfirm, Space, Tag } from 'antd'
import { DeleteOutlined, DragOutlined, SelectOutlined, UndoOutlined } from '@ant-design/icons'
import { Rect, Transformer, Arrow } from 'react-konva'
import type Konva from 'konva'
import type { AnnotationTask } from '@/types/annotation'
import { getMessageInstance } from '@/utils/messageHolder'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import type { AnnotationRegion, ImageDimensions } from '../hooks/useAnnotationRegions'

// ── Props ───────────────────────────────────────────────────────────────────

interface ObjectDetectionAnnotatorProps {
  task: AnnotationTask
  objectConfig?: LabelStudioObjectConfig
  controlConfig: LabelStudioControlConfig
  readOnly?: boolean
  /** 共享区域状态 */
  regions: AnnotationRegion[]
  selectedRegionId: string | null
  imageDimensions: ImageDimensions | null
  onAddRegion: (region: AnnotationRegion) => void
  onUpdateRegion: (
    id: string,
    updates: Partial<Pick<AnnotationRegion, 'spatial' | 'label'>>,
  ) => void
  onDeleteRegion: (id: string) => void
  onSelectRegion: (id: string | null) => void
  onImageDimensionsChange: (dims: ImageDimensions) => void
  /** Relation arrows to render */
  relations?: Array<{ id: string; fromRegionId: string; toRegionId: string; label?: string }>
}

type ToolMode = 'select' | 'draw'

// ── Helpers ─────────────────────────────────────────────────────────────────

interface LocalBBox {
  id: string
  x: number
  y: number
  width: number
  height: number
  label: string
}

function regionToBBox(r: AnnotationRegion): LocalBBox {
  return {
    id: r.id,
    x: r.spatial.x,
    y: r.spatial.y,
    width: r.spatial.width,
    height: r.spatial.height,
    label: r.label ?? '',
  }
}

/** Stable serialization of regions for effect dependency comparison */
function regionIds(regions: AnnotationRegion[]): string {
  return regions.map((r) => r.id).join(',')
}

// ── Component ───────────────────────────────────────────────────────────────

export default function ObjectDetectionAnnotator({
  task,
  objectConfig,
  controlConfig,
  readOnly = false,
  regions,
  selectedRegionId,
  imageDimensions,
  onAddRegion,
  onUpdateRegion,
  onDeleteRegion,
  onSelectRegion,
  onImageDimensionsChange,
  relations = [],
}: ObjectDetectionAnnotatorProps) {
  const hasLabels = controlConfig.type === 'rectanglelabels'
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined
  const zp = useZoomPan(imageUrl)

  const [toolMode, setToolMode] = useState<ToolMode>('draw')
  const [activeLabel, setActiveLabel] = useState<string | null>(
    hasLabels ? (controlConfig.choices[0]?.value ?? null) : null,
  )
  const [drawing, setDrawing] = useState<{ x: number; y: number; w: number; h: number } | null>(
    null,
  )
  const transformerRef = useRef<Konva.Transformer>(null)
  const [showTransformer, setShowTransformer] = useState(false)

  // Reset tool state on task change
  useEffect(() => {
    setToolMode('draw')
    setDrawing(null)
    setShowTransformer(false)
    if (hasLabels) setActiveLabel(controlConfig.choices[0]?.value ?? null)
  }, [task.id, hasLabels, controlConfig.choices])

  // Track image dimensions (once)
  useEffect(() => {
    if (zp.image && !imageDimensions) {
      onImageDimensionsChange({ width: zp.image.width, height: zp.image.height })
    }
  }, [zp.image, imageDimensions, onImageDimensionsChange])

  // Stable snapshot of region ids to avoid Transformer sync on every spatial change
  const regionIdSnapshot = regionIds(regions)

  // Sync Transformer — only when selection or region count changes
  useEffect(() => {
    const transformer = transformerRef.current
    const stage = zp.stageRef.current
    if (!transformer || !stage) return
    const node = selectedRegionId ? stage.findOne(`#${selectedRegionId}`) : null
    transformer.nodes(node ? [node] : [])
    transformer.getLayer()?.batchDraw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRegionId, regionIdSnapshot])

  const bboxes = useMemo<LocalBBox[]>(() => regions.map(regionToBBox), [regions])

  // Stable undo: ref avoids re-registering the Ctrl+Z listener on every region change
  const regionsRef = useRef(regions)
  regionsRef.current = regions

  const handleDelete = useCallback(
    (id: string) => {
      onDeleteRegion(id)
    },
    [onDeleteRegion],
  )

  const handleUndo = useCallback(() => {
    const regs = regionsRef.current
    const last = regs[regs.length - 1]
    if (last) onDeleteRegion(last.id)
    onSelectRegion(null)
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

  const onMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective || toolMode !== 'draw') return
      if (e.evt.button !== 0) return
      // Only start drawing on empty canvas, not when clicking on existing shapes
      if (e.target !== e.target.getStage()) return
      // Hide transform handles when starting to draw a new box
      setShowTransformer(false)
      const p = zp.pointerToImage()
      if (!p) return
      setDrawing({ x: p.x, y: p.y, w: 0, h: 0 })
    },
    [readOnly, zp, toolMode],
  )

  const onMouseMove = useCallback(() => {
    if (!drawing) return
    const p = zp.pointerToImage()
    if (!p) return
    setDrawing((prev) => (prev ? { ...prev, w: p.x - prev.x, h: p.y - prev.y } : null))
  }, [drawing, zp])

  const onMouseUp = useCallback(() => {
    if (!drawing) return
    const { x, y, w, h } = drawing
    setDrawing(null)
    if (Math.abs(w) < 3 || Math.abs(h) < 3) return
    if (hasLabels && !activeLabel) {
      getMessageInstance()?.warning('请先选择标签(点击或按数字键 1-9)')
      return
    }
    onAddRegion({
      id: crypto.randomUUID(),
      type: 'rectangle',
      label: activeLabel ?? undefined,
      spatial: {
        x: w < 0 ? x + w : x,
        y: h < 0 ? y + h : y,
        width: Math.abs(w),
        height: Math.abs(h),
      },
      sourceControlName: controlConfig.name,
      perRegionResults: {},
    })
  }, [drawing, hasLabels, activeLabel, controlConfig.name, onAddRegion])

  const toolbar = readOnly ? null : (
    <Space.Compact>
      <Button
        type={toolMode === 'draw' ? 'primary' : 'default'}
        icon={<DragOutlined />}
        onClick={() => {
          setToolMode('draw')
          onSelectRegion(null)
          setShowTransformer(false)
        }}
      >
        绘制
      </Button>
      <Button
        type={toolMode === 'select' ? 'primary' : 'default'}
        icon={<SelectOutlined />}
        onClick={() => {
          setToolMode('select')
          setShowTransformer(false)
        }}
      >
        选择
      </Button>
    </Space.Compact>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
      {!readOnly && hasLabels && (
        <LabelPalette
          labels={controlConfig.choices.map((c) => c.value)}
          activeLabel={activeLabel}
          onChange={setActiveLabel}
        />
      )}

      <div style={{ flex: 1, position: 'relative', minHeight: 400 }}>
        <ZoomPanImageStage
          controller={zp}
          toolbarExtra={
            <Space>
              {toolbar}
              {!readOnly && (
                <>
                  <Button
                    icon={<UndoOutlined />}
                    onClick={handleUndo}
                    disabled={bboxes.length === 0}
                  >
                    撤销
                  </Button>
                  <Popconfirm
                    title="确认删除?"
                    onConfirm={() => selectedRegionId && handleDelete(selectedRegionId)}
                    disabled={!selectedRegionId}
                  >
                    <Button icon={<DeleteOutlined />} disabled={!selectedRegionId}>
                      删除选中
                    </Button>
                  </Popconfirm>
                  <Tag>{bboxes.length} 个区域</Tag>
                </>
              )}
            </Space>
          }
          onStageMouseDown={onMouseDown}
          onStageMouseMove={onMouseMove}
          onStageMouseUp={onMouseUp}
          renderContent={({ visibleStrokeWidth, visibleAnchorSize }) => (
            <>
              {bboxes.map((bbox, i) => (
                <Rect
                  key={bbox.id}
                  id={bbox.id}
                  x={bbox.x}
                  y={bbox.y}
                  width={bbox.width}
                  height={bbox.height}
                  stroke={labelColor(i)}
                  strokeWidth={visibleStrokeWidth(2)}
                  fill={`${labelColor(i)}20`}
                  draggable={!readOnly && !zp.panEffective}
                  onClick={() => {
                    if (!readOnly) {
                      onSelectRegion(selectedRegionId === bbox.id ? null : bbox.id)
                      setShowTransformer(false)
                    }
                  }}
                  onTap={() => {
                    if (!readOnly) {
                      onSelectRegion(selectedRegionId === bbox.id ? null : bbox.id)
                    }
                  }}
                  onContextMenu={(e) => {
                    e.evt.preventDefault()
                    if (!readOnly) {
                      onSelectRegion(bbox.id)
                      setShowTransformer(true)
                    }
                  }}
                  onDragEnd={(e) => {
                    const node = e.target
                    onUpdateRegion(bbox.id, {
                      spatial: { x: node.x(), y: node.y(), width: bbox.width, height: bbox.height },
                    })
                  }}
                  onTransformEnd={(e) => {
                    const node = e.target
                    const newW = Math.max(3, node.width() * node.scaleX())
                    const newH = Math.max(3, node.height() * node.scaleY())
                    onUpdateRegion(bbox.id, {
                      spatial: { x: node.x(), y: node.y(), width: newW, height: newH },
                    })
                    node.scaleX(1)
                    node.scaleY(1)
                  }}
                />
              ))}
              {drawing && (
                <Rect
                  x={drawing.w < 0 ? drawing.x + drawing.w : drawing.x}
                  y={drawing.h < 0 ? drawing.y + drawing.h : drawing.y}
                  width={Math.abs(drawing.w)}
                  height={Math.abs(drawing.h)}
                  stroke="#1677FF"
                  strokeWidth={visibleStrokeWidth(2)}
                  dash={[4, 4]}
                />
              )}
              {selectedRegionId && !readOnly && showTransformer && (
                <Transformer
                  ref={transformerRef}
                  anchorSize={visibleAnchorSize()}
                  borderStrokeWidth={visibleStrokeWidth(1.5)}
                  boundBoxFunc={(oldBox, newBox) =>
                    newBox.width < 5 || newBox.height < 5 ? oldBox : newBox
                  }
                />
              )}
              {/* Render relation arrows */}
              {relations.map((rel) => {
                const fromRegion = regions.find((r) => r.id === rel.fromRegionId)
                const toRegion = regions.find((r) => r.id === rel.toRegionId)
                if (!fromRegion || !toRegion) return null
                const fx = fromRegion.spatial.x + fromRegion.spatial.width / 2
                const fy = fromRegion.spatial.y + fromRegion.spatial.height / 2
                const tx = toRegion.spatial.x + toRegion.spatial.width / 2
                const ty = toRegion.spatial.y + toRegion.spatial.height / 2
                return (
                  <Arrow
                    key={rel.id}
                    points={[fx, fy, tx, ty]}
                    stroke="#FF6B00"
                    fill="#FF6B00"
                    strokeWidth={visibleStrokeWidth(2)}
                    pointerLength={10}
                    pointerWidth={8}
                  />
                )
              })}
            </>
          )}
        />
      </div>
      {/* Region list — placed below canvas to avoid occluding the image */}
      {bboxes.length > 0 && (
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
            dataSource={bboxes}
            renderItem={(item: LocalBBox, i: number) => (
              <List.Item
                style={{
                  padding: '4px 12px',
                  cursor: 'pointer',
                  background:
                    selectedRegionId === item.id ? 'var(--ant-color-primary-bg)' : undefined,
                }}
                onClick={() => {
                  onSelectRegion(item.id)
                  setShowTransformer(false)
                }}
              >
                <Space>
                  <Tag color={labelColor(i)}>{i + 1}</Tag>
                  <span>{item.label || `区域 ${i + 1}`}</span>
                </Space>
                {!readOnly && (
                  <Button
                    type="text"
                    size="small"
                    icon={<DeleteOutlined />}
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDelete(item.id)
                    }}
                  />
                )}
              </List.Item>
            )}
          />
        </div>
      )}
    </div>
  )
}
