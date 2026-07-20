import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Space, Tag } from 'antd'
import { DeleteOutlined, UndoOutlined } from '@ant-design/icons'
import { Circle } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import type { Region } from '../hooks/useAnnotationRegions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'
import { regionsOf } from '../utils/regions'

// ── Constants ───────────────────────────────────────────────────────────────

const KEYPOINT_VISUAL_RADIUS = 6

// ── Component ───────────────────────────────────────────────────────────────

export default function KeyPointAnnotator({
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
  const hasLabels = controlConfig.type === 'keypointlabels'
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined
  const zp = useZoomPan(imageUrl)

  const [activeLabel, setActiveLabel] = useState<string | null>(
    hasLabels ? (controlConfig.choices[0]?.value ?? null) : null,
  )

  // Reset on task change
  useEffect(() => {
    if (hasLabels) setActiveLabel(controlConfig.choices[0]?.value ?? null)
  }, [task.id, hasLabels, controlConfig.choices])

  // Track image dimensions
  useEffect(() => {
    if (zp.image && !imageDimensions) {
      onImageDimensionsChange({ width: zp.image.width, height: zp.image.height })
    }
  }, [zp.image, imageDimensions, onImageDimensionsChange])

  // Filter keypoint regions from this control
  const kpRegions = useMemo(
    () => regionsOf(regions, controlConfig.name, 'keypoint'),
    [regions, controlConfig.name],
  )

  const handleClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective) return
      if (e.evt.button !== 0) return
      // Only add point when clicking on empty canvas, not on existing keypoints
      if (e.target !== e.target.getStage()) return
      const p = zp.pointerToImage()
      if (!p) return
      if (hasLabels && !activeLabel) {
        getMessageInstance()?.warning('请先选择标签(点击或按数字键 1-9)')
        return
      }
      onAddRegion({
        id: crypto.randomUUID(),
        fromName: controlConfig.name,
        label: activeLabel ?? undefined,
        value: { kind: 'keypoint', x: p.x, y: p.y, width: KEYPOINT_VISUAL_RADIUS * 2 },
        perRegionResults: {},
      })
    },
    [readOnly, zp, hasLabels, activeLabel, controlConfig.name, onAddRegion],
  )

  const handleDelete = useCallback(
    (id: string) => {
      onDeleteRegion(id)
    },
    [onDeleteRegion],
  )

  // Stable ref to avoid Ctrl+Z handler re-registration on every region change
  const kpRegionsRef = useRef(kpRegions)
  kpRegionsRef.current = kpRegions

  // Ctrl+Z
  useEffect(() => {
    if (readOnly) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        const regs = kpRegionsRef.current
        const last = regs[regs.length - 1]
        if (last) onDeleteRegion(last.id)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [readOnly, onDeleteRegion])

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
            !readOnly && (
              <Space>
                <Button
                  icon={<UndoOutlined />}
                  disabled={kpRegions.length === 0}
                  onClick={() => {
                    const last = kpRegions[kpRegions.length - 1]
                    if (last) onDeleteRegion(last.id)
                  }}
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
                <Tag>{kpRegions.length} 个关键点</Tag>
              </Space>
            )
          }
          onStageClick={handleClick}
          renderContent={({ visibleStrokeWidth, visibleAnchorSize }) => {
            const radius = Math.max(3, visibleAnchorSize() / 2)
            return (
              <>
                {kpRegions.map((kp, i) => {
                  const idx = controlConfig.choices.findIndex((c) => c.value === kp.label)
                  const color = labelColor(Math.max(0, idx >= 0 ? idx : i))
                  return (
                    <Circle
                      key={kp.id}
                      id={kp.id}
                      x={kp.value.x}
                      y={kp.value.y}
                      radius={radius}
                      fill={color}
                      stroke="#fff"
                      strokeWidth={visibleStrokeWidth(2)}
                      draggable={!readOnly && !zp.panEffective}
                      onClick={() => {
                        if (!readOnly) onSelectRegion(selectedRegionId === kp.id ? null : kp.id)
                      }}
                      onContextMenu={(e) => {
                        e.evt.preventDefault()
                        if (!readOnly) onSelectRegion(kp.id)
                      }}
                      onDragEnd={(e) => {
                        const node = e.target
                        onUpdateRegion(kp.id, {
                          value: {
                            kind: 'keypoint',
                            x: node.x(),
                            y: node.y(),
                            width: KEYPOINT_VISUAL_RADIUS * 2,
                          },
                        })
                      }}
                    />
                  )
                })}
              </>
            )
          }}
        />
      </div>
      {/* Region list — placed below canvas to avoid occluding the image */}
      {kpRegions.length > 0 && (
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
            dataSource={kpRegions}
            renderItem={(region: Region, i: number) => {
              const idx = controlConfig.choices.findIndex((c) => c.value === region.label)
              const color = labelColor(Math.max(0, idx >= 0 ? idx : i))
              return (
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
                    <Tag color={color}>{i + 1}</Tag>
                    <span>{region.label || `点 ${i + 1}`}</span>
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
              )
            }}
          />
        </div>
      )}
    </div>
  )
}
