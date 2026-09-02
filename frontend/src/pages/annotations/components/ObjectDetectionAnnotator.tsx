import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Popconfirm, Space, Tag } from 'antd'
import { DeleteOutlined, DragOutlined, SelectOutlined, UndoOutlined } from '@ant-design/icons'
import { Rect, Transformer, Arrow } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import type { Region } from '../hooks/useAnnotationRegions'
import { regionsOf, regionCenter } from '../utils/regions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'

// ── Props ───────────────────────────────────────────────────────────────────

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

/** Stable serialization of regions for effect dependency comparison */
function regionIds(regions: Region[]): string {
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
}: SpatialAnnotatorProps) {
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

  // 仅本控件的矩形区域
  const rectRegions = useMemo(
    () => regionsOf(regions, controlConfig.name, 'rectangle'),
    [regions, controlConfig.name],
  )
  const bboxes = useMemo<LocalBBox[]>(
    () =>
      rectRegions.map((r) => ({
        id: r.id,
        x: r.value.x,
        y: r.value.y,
        width: r.value.width,
        height: r.value.height,
        label: r.label ?? '',
      })),
    [rectRegions],
  )

  // Stable undo: ref avoids re-registering the Ctrl+Z listener on every region change
  const regionsRef = useRef(rectRegions)
  regionsRef.current = rectRegions

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
      fromName: controlConfig.name,
      label: activeLabel ?? undefined,
      value: {
        kind: 'rectangle',
        x: w < 0 ? x + w : x,
        y: h < 0 ? y + h : y,
        width: Math.abs(w),
        height: Math.abs(h),
        rotation: 0,
      },
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
                      value: {
                        kind: 'rectangle',
                        x: node.x(),
                        y: node.y(),
                        width: bbox.width,
                        height: bbox.height,
                        rotation: 0,
                      },
                    })
                  }}
                  onTransformEnd={(e) => {
                    const node = e.target
                    const newW = Math.max(3, node.width() * node.scaleX())
                    const newH = Math.max(3, node.height() * node.scaleY())
                    onUpdateRegion(bbox.id, {
                      value: {
                        kind: 'rectangle',
                        x: node.x(),
                        y: node.y(),
                        width: newW,
                        height: newH,
                        rotation: 0,
                      },
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
                  stroke="#1890FF"
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
                const from = regionCenter(fromRegion)
                const to = regionCenter(toRegion)
                if (!from || !to) return null
                return (
                  <Arrow
                    key={rel.id}
                    points={[from.x, from.y, to.x, to.y]}
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
