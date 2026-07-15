import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Space, Tag, Typography } from 'antd'
import { BorderOutlined, DeleteOutlined, SelectOutlined, UndoOutlined } from '@ant-design/icons'
import { Line } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import type { AnnotationRegion } from '../hooks/useAnnotationRegions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Flatten polygon points to Konva flat array format [x0,y0,x1,y1,...] */
function toFlatPoints(pts: [number, number][]): number[] {
  return pts.flat()
}

// ── Component ───────────────────────────────────────────────────────────────

export default function ImageSegmentationAnnotator({
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
  const hasLabels = controlConfig.type === 'polygonlabels'
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined
  const zp = useZoomPan(imageUrl)

  type ToolMode = 'select' | 'draw'
  const [toolMode, setToolMode] = useState<ToolMode>('draw')
  const [activeLabel, setActiveLabel] = useState<string | null>(
    hasLabels ? controlConfig.choices[0]?.value ?? null : null,
  )
  const [currentPoints, setCurrentPoints] = useState<[number, number][]>([])

  // Reset tool state on task change
  useEffect(() => {
    setToolMode('draw')
    setCurrentPoints([])
    if (hasLabels) setActiveLabel(controlConfig.choices[0]?.value ?? null)
  }, [task.id, hasLabels, controlConfig.choices])

  // Track image dimensions
  useEffect(() => {
    if (zp.image && !imageDimensions) {
      onImageDimensionsChange({ width: zp.image.width, height: zp.image.height })
    }
  }, [zp.image, imageDimensions, onImageDimensionsChange])

  const handleUndoPoint = useCallback(() => {
    setCurrentPoints((prev) => prev.slice(0, -1))
  }, [])

  // Stable refs to avoid re-registering the Ctrl+Z listener on every point/region change
  const currentPointsRef = useRef(currentPoints)
  currentPointsRef.current = currentPoints
  const regionsRef = useRef(regions)
  regionsRef.current = regions

  // Ctrl+Z
  useEffect(() => {
    if (readOnly) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        if (currentPointsRef.current.length > 0) handleUndoPoint()
        else {
          const regs = regionsRef.current
          const last = regs[regs.length - 1]
          if (last) onDeleteRegion(last.id)
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [readOnly, handleUndoPoint, onDeleteRegion])

  // Filter to only polygon regions from this control
  const polyRegions = useMemo(
    () => regions.filter((r) => r.sourceControlName === controlConfig.name && r.type === 'polygon'),
    [regions, controlConfig.name],
  )

  const finishPolygon = useCallback(() => {
    if (currentPoints.length < 3) return
    if (hasLabels && !activeLabel) {
      getMessageInstance()?.warning('请先选择标签(点击或按数字键 1-9)')
      return
    }
    // Compute bounding box from points
    const xs = currentPoints.map((p) => p[0])
    const ys = currentPoints.map((p) => p[1])
    const minX = Math.min(...xs)
    const minY = Math.min(...ys)
    onAddRegion({
      id: crypto.randomUUID(),
      type: 'polygon',
      label: activeLabel ?? undefined,
      spatial: {
        x: minX,
        y: minY,
        width: Math.max(...xs) - minX,
        height: Math.max(...ys) - minY,
        points: [...currentPoints],
      },
      sourceControlName: controlConfig.name,
      perRegionResults: {},
    })
    setCurrentPoints([])
  }, [currentPoints, hasLabels, activeLabel, controlConfig.name, onAddRegion])

  // Stage handlers
  const onStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective || toolMode !== 'draw') return
      if (e.evt.button !== 0) return
      // Only add vertex on empty canvas, not when clicking on existing polygons
      if (e.target !== e.target.getStage()) return
      const p = zp.pointerToImage()
      if (!p) return
      setCurrentPoints((prev) => [...prev, [p.x, p.y]])
    },
    [readOnly, zp, toolMode],
  )

  const onStageDblClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective || toolMode !== 'draw') return
      e.evt.preventDefault()
      finishPolygon()
    },
    [readOnly, zp, toolMode, finishPolygon],
  )

  const handleDelete = useCallback(
    (id: string) => {
      onDeleteRegion(id)
    },
    [onDeleteRegion],
  )

  const toolbar = readOnly ? null : (
    <Space.Compact>
      <Button
        type={toolMode === 'draw' ? 'primary' : 'default'}
        icon={<BorderOutlined />}
        onClick={() => { setToolMode('draw'); onSelectRegion(null) }}
      >
        绘制
      </Button>
      <Button
        type={toolMode === 'select' ? 'primary' : 'default'}
        icon={<SelectOutlined />}
        onClick={() => { setToolMode('select'); setCurrentPoints([]) }}
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
                  {toolMode === 'draw' && currentPoints.length >= 3 && (
                    <Button type="dashed" onClick={finishPolygon}>
                      闭合 ({currentPoints.length} 点)
                    </Button>
                  )}
                  {toolMode === 'draw' && currentPoints.length > 0 && (
                    <Button icon={<UndoOutlined />} onClick={handleUndoPoint}>
                      撤销顶点
                    </Button>
                  )}
                  <Button
                    icon={<DeleteOutlined />}
                    disabled={!selectedRegionId}
                    onClick={() => selectedRegionId && onDeleteRegion(selectedRegionId)}
                  >
                    删除选中
                  </Button>
                  <Tag>{polyRegions.length} 个区域</Tag>
                </>
              )}
            </Space>
          }
          onStageClick={onStageClick}
          onStageDblClick={onStageDblClick}
          renderContent={({ visibleStrokeWidth }) => (
            <>
              {polyRegions.map((region, i) => {
                const pts = region.spatial.points ?? []
                return (
                  <Line
                    key={region.id}
                    id={region.id}
                    points={toFlatPoints(pts)}
                    closed
                    stroke={labelColor(i)}
                    strokeWidth={visibleStrokeWidth(2)}
                    fill={`${labelColor(i)}30`}
                    draggable={!readOnly && toolMode === 'select' && !zp.panEffective}
                    onClick={() => {
                      if (!readOnly) onSelectRegion(selectedRegionId === region.id ? null : region.id)
                    }}
                    onContextMenu={(e) => {
                      e.evt.preventDefault()
                      if (!readOnly) onSelectRegion(region.id)
                    }}
                    onDragEnd={(e) => {
                      const node = e.target
                      const dx = node.x()
                      const dy = node.y()
                      const newPoints: [number, number][] = pts.map(
                        ([px, py]) => [px + dx, py + dy],
                      )
                      const xs = newPoints.map((p) => p[0])
                      const ys = newPoints.map((p) => p[1])
                      onUpdateRegion(region.id, {
                        spatial: {
                          ...region.spatial,
                          x: Math.min(...xs),
                          y: Math.min(...ys),
                          width: Math.max(...xs) - Math.min(...xs),
                          height: Math.max(...ys) - Math.min(...ys),
                          points: newPoints,
                        },
                      })
                      node.position({ x: 0, y: 0 })
                    }}
                  />
                )
              })}
              {currentPoints.length > 0 && (
                <Line
                  points={toFlatPoints(currentPoints)}
                  stroke="#1677FF"
                  strokeWidth={visibleStrokeWidth(2)}
                  dash={[4, 4]}
                />
              )}
            </>
          )}
        />

      </div>
      {/* Region list — placed below canvas to avoid occluding the image */}
      {polyRegions.length > 0 && (
        <div style={{
          maxHeight: 120,
          overflowY: 'auto',
          background: 'var(--ant-color-bg-container)',
          border: '1px solid var(--ant-color-border)',
          borderRadius: 6,
          flexShrink: 0,
        }}>
          <List
            size="small"
            dataSource={polyRegions}
            renderItem={(region: AnnotationRegion, i: number) => (
              <List.Item
                style={{
                  padding: '4px 12px',
                  cursor: 'pointer',
                  background: selectedRegionId === region.id ? 'var(--ant-color-primary-bg)' : undefined,
                }}
                onClick={() => onSelectRegion(region.id)}
              >
                <Space>
                  <Tag color={labelColor(i)}>{i + 1}</Tag>
                  <span>{region.label || `区域 ${i + 1}`}</span>
                </Space>
                {!readOnly && (
                  <Button
                    type="text" size="small" icon={<DeleteOutlined />}
                    onClick={(e) => { e.stopPropagation(); handleDelete(region.id) }}
                  />
                )}
              </List.Item>
            )}
          />
        </div>
      )}

      {!readOnly && toolMode === 'draw' && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          点击添加顶点，双击或点「闭合」结束多边形（至少 3 个顶点）。
        </Typography.Text>
      )}
    </div>
  )
}
