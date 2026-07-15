import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Space, Tag } from 'antd'
import { DeleteOutlined, DragOutlined, SelectOutlined, UndoOutlined } from '@ant-design/icons'
import { Ellipse, Transformer } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import type { AnnotationRegion } from '../hooks/useAnnotationRegions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Stable serialization of region ids for effect dependency comparison */
function regionIds(regions: AnnotationRegion[]): string {
  return regions.map((r) => r.id).join(',')
}

// ── Component ───────────────────────────────────────────────────────────────

export default function EllipseAnnotator({
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
}: SpatialAnnotatorProps) {
  const hasLabels = controlConfig.type === 'ellipselabels'
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined
  const zp = useZoomPan(imageUrl)

  type ToolMode = 'select' | 'draw'
  const [toolMode, setToolMode] = useState<ToolMode>('draw')
  const [activeLabel, setActiveLabel] = useState<string | null>(
    hasLabels ? (controlConfig.choices[0]?.value ?? null) : null,
  )
  const [drawing, setDrawing] = useState<{ x: number; y: number; rx: number; ry: number } | null>(
    null,
  )
  const transformerRef = useRef<Konva.Transformer>(null)
  const [showTransformer, setShowTransformer] = useState(false)

  // Reset on task change
  useEffect(() => {
    setToolMode('draw')
    setDrawing(null)
    setShowTransformer(false)
    if (hasLabels) setActiveLabel(controlConfig.choices[0]?.value ?? null)
  }, [task.id, hasLabels, controlConfig.choices])

  // Track image dimensions
  useEffect(() => {
    if (zp.image && !imageDimensions) {
      onImageDimensionsChange({ width: zp.image.width, height: zp.image.height })
    }
  }, [zp.image, imageDimensions, onImageDimensionsChange])

  // Filter ellipse regions from this control
  const ellipseRegions = useMemo(
    () => regions.filter((r) => r.sourceControlName === controlConfig.name && r.type === 'ellipse'),
    [regions, controlConfig.name],
  )

  // Stable snapshot of region ids
  const regionIdSnapshot = regionIds(regions)

  // Sync Transformer
  useEffect(() => {
    const transformer = transformerRef.current
    const stage = zp.stageRef.current
    if (!transformer || !stage) return
    const node = selectedRegionId ? stage.findOne(`#${selectedRegionId}`) : null
    transformer.nodes(node ? [node] : [])
    transformer.getLayer()?.batchDraw()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRegionId, regionIdSnapshot])

  // Stable ref to avoid Ctrl+Z handler re-registration on every region change
  const ellipseRegionsRef = useRef(ellipseRegions)
  ellipseRegionsRef.current = ellipseRegions

  const handleUndo = useCallback(() => {
    const regs = ellipseRegionsRef.current
    const last = regs[regs.length - 1]
    if (last) {
      onDeleteRegion(last.id)
      onSelectRegion(null)
    }
  }, [onDeleteRegion, onSelectRegion])

  const handleDelete = useCallback(
    (id: string) => {
      onDeleteRegion(id)
    },
    [onDeleteRegion],
  )

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
      // Hide transform handles when starting to draw a new ellipse
      setShowTransformer(false)
      const p = zp.pointerToImage()
      if (!p) return
      setDrawing({ x: p.x, y: p.y, rx: 0, ry: 0 })
    },
    [readOnly, zp, toolMode],
  )

  const onMouseMove = useCallback(() => {
    if (!drawing) return
    const p = zp.pointerToImage()
    if (!p) return
    setDrawing((prev) => (prev ? { ...prev, rx: p.x - prev.x, ry: p.y - prev.y } : null))
  }, [drawing, zp])

  const onMouseUp = useCallback(() => {
    if (!drawing) return
    const { x, y, rx, ry } = drawing
    setDrawing(null)
    if (Math.abs(rx) < 3 && Math.abs(ry) < 3) return
    if (hasLabels && !activeLabel) {
      getMessageInstance()?.warning('请先选择标签(点击或按数字键 1-9)')
      return
    }
    const cx = rx < 0 ? x + rx : x
    const cy = ry < 0 ? y + ry : y
    onAddRegion({
      id: crypto.randomUUID(),
      type: 'ellipse',
      label: activeLabel ?? undefined,
      spatial: {
        x: cx,
        y: cy,
        width: Math.abs(rx),
        height: Math.abs(ry),
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
                    disabled={ellipseRegions.length === 0}
                  >
                    撤销
                  </Button>
                  <Button
                    icon={<DeleteOutlined />}
                    disabled={!selectedRegionId}
                    onClick={() => selectedRegionId && onDeleteRegion(selectedRegionId)}
                  >
                    删除选中
                  </Button>
                  <Tag>{ellipseRegions.length} 个椭圆</Tag>
                </>
              )}
            </Space>
          }
          onStageMouseDown={onMouseDown}
          onStageMouseMove={onMouseMove}
          onStageMouseUp={onMouseUp}
          renderContent={({ visibleStrokeWidth, visibleAnchorSize }) => (
            <>
              {ellipseRegions.map((region, i) => (
                <Ellipse
                  key={region.id}
                  id={region.id}
                  x={region.spatial.x + region.spatial.width / 2}
                  y={region.spatial.y + region.spatial.height / 2}
                  radiusX={region.spatial.width / 2}
                  radiusY={region.spatial.height / 2}
                  stroke={labelColor(i)}
                  strokeWidth={visibleStrokeWidth(2)}
                  fill={`${labelColor(i)}20`}
                  draggable={!readOnly && !zp.panEffective}
                  onClick={() => {
                    if (!readOnly) {
                      onSelectRegion(selectedRegionId === region.id ? null : region.id)
                      setShowTransformer(false)
                    }
                  }}
                  onTap={() => {
                    if (!readOnly) {
                      onSelectRegion(selectedRegionId === region.id ? null : region.id)
                      setShowTransformer(false)
                    }
                  }}
                  onContextMenu={(e) => {
                    e.evt.preventDefault()
                    if (!readOnly) {
                      onSelectRegion(region.id)
                      setShowTransformer(true)
                    }
                  }}
                  onDragEnd={(e) => {
                    const node = e.target
                    const x = node.x() - region.spatial.width / 2
                    const y = node.y() - region.spatial.height / 2
                    onUpdateRegion(region.id, {
                      spatial: { ...region.spatial, x, y },
                    })
                  }}
                  onTransformEnd={(e) => {
                    const node = e.target as Konva.Ellipse
                    const newRX = Math.max(3, node.radiusX() * node.scaleX())
                    const newRY = Math.max(3, node.radiusY() * node.scaleY())
                    const rot = node.rotation()
                    onUpdateRegion(region.id, {
                      spatial: {
                        x: node.x() - newRX,
                        y: node.y() - newRY,
                        width: newRX * 2,
                        height: newRY * 2,
                        rotation: rot,
                      },
                    })
                    node.scaleX(1)
                    node.scaleY(1)
                  }}
                />
              ))}
              {drawing && (
                <Ellipse
                  x={drawing.rx < 0 ? drawing.x + drawing.rx / 2 : drawing.x + drawing.rx / 2}
                  y={drawing.ry < 0 ? drawing.y + drawing.ry / 2 : drawing.y + drawing.ry / 2}
                  radiusX={Math.abs(drawing.rx) / 2}
                  radiusY={Math.abs(drawing.ry) / 2}
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
                  enabledAnchors={['top-left', 'top-right', 'bottom-left', 'bottom-right']}
                  boundBoxFunc={(oldBox, newBox) =>
                    newBox.width < 5 || newBox.height < 5 ? oldBox : newBox
                  }
                />
              )}
            </>
          )}
        />
      </div>
      {/* Region list — placed below canvas to avoid occluding the image */}
      {ellipseRegions.length > 0 && (
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
            dataSource={ellipseRegions}
            renderItem={(region: AnnotationRegion, i: number) => (
              <List.Item
                style={{
                  padding: '4px 12px',
                  cursor: 'pointer',
                  background:
                    selectedRegionId === region.id ? 'var(--ant-color-primary-bg)' : undefined,
                }}
                onClick={() => {
                  onSelectRegion(region.id)
                  setShowTransformer(false)
                }}
              >
                <Space>
                  <Tag color={labelColor(i)}>{i + 1}</Tag>
                  <span>{region.label || `椭圆 ${i + 1}`}</span>
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
    </div>
  )
}
