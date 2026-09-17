import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, List, Space, Tag, Typography } from 'antd'
import { DeleteOutlined, SelectOutlined, UndoOutlined } from '@ant-design/icons'
import { Line } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { useZoomPan } from './useZoomPan'
import ZoomPanImageStage from './ZoomPanImageStage'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import type { Region, VectorValue, VectorVertex } from '../hooks/useAnnotationRegions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'
import { regionsOf } from '../utils/regions'
import { generateId } from '../utils/id'

function toFlatPoints(vertices: VectorVertex[]): number[] {
  return vertices.flatMap((v) => [v.x, v.y])
}

/**
 * Vector / VectorLabels 标注器 —— 点击添加顶点（每点 id + prevPointId 链表），
 * 双击或「闭合/完成」结束。MVP 无贝塞尔（isBezier 全 false）；贝塞尔控制点为增强。
 */
export default function VectorAnnotator({
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
  const hasLabels = controlConfig.type === 'vectorlabels'
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined
  const zp = useZoomPan(imageUrl)

  type ToolMode = 'select' | 'draw'
  const [toolMode, setToolMode] = useState<ToolMode>('draw')
  const [activeLabel, setActiveLabel] = useState<string | null>(
    hasLabels ? (controlConfig.choices[0]?.value ?? null) : null,
  )
  const [currentVertices, setCurrentVertices] = useState<VectorVertex[]>([])

  useEffect(() => {
    setToolMode('draw')
    setCurrentVertices([])
    if (hasLabels) setActiveLabel(controlConfig.choices[0]?.value ?? null)
  }, [task.id, hasLabels, controlConfig.choices])

  useEffect(() => {
    if (zp.image && !imageDimensions) {
      onImageDimensionsChange({ width: zp.image.width, height: zp.image.height })
    }
  }, [zp.image, imageDimensions, onImageDimensionsChange])

  const handleUndoVertex = useCallback(() => setCurrentVertices((prev) => prev.slice(0, -1)), [])

  const currentVerticesRef = useRef(currentVertices)
  currentVerticesRef.current = currentVertices
  const regionsRef = useRef(regions)
  regionsRef.current = regions

  useEffect(() => {
    if (readOnly) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault()
        if (currentVerticesRef.current.length > 0) handleUndoVertex()
        else {
          const regs = regionsRef.current
          const last = regs[regs.length - 1]
          if (last) onDeleteRegion(last.id)
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [readOnly, handleUndoVertex, onDeleteRegion])

  const vecRegions = useMemo<Array<Region & { value: VectorValue }>>(
    () => regionsOf(regions, controlConfig.name, 'vector'),
    [regions, controlConfig.name],
  )

  const finishVector = useCallback(
    (close: boolean) => {
      if (currentVertices.length < 2) return
      if (hasLabels && !activeLabel) {
        getMessageInstance()?.warning('请先选择标签(点击或按数字键 1-9)')
        return
      }
      onAddRegion({
        id: generateId(),
        fromName: controlConfig.name,
        label: activeLabel ?? undefined,
        value: { kind: 'vector', vertices: [...currentVertices], closed: close },
        perRegionResults: {},
      })
      setCurrentVertices([])
    },
    [currentVertices, hasLabels, activeLabel, controlConfig.name, onAddRegion],
  )

  const onStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective || toolMode !== 'draw') return
      if (e.evt.button !== 0) return
      if (e.target !== e.target.getStage()) return
      const p = zp.pointerToImage()
      if (!p) return
      setCurrentVertices((prev) => [
        ...prev,
        {
          id: generateId(),
          x: p.x,
          y: p.y,
          prevPointId: prev.length > 0 ? prev[prev.length - 1].id : null,
          isBezier: false,
        },
      ])
    },
    [readOnly, zp, toolMode],
  )

  const onStageDblClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>) => {
      if (readOnly || zp.panEffective || toolMode !== 'draw') return
      e.evt.preventDefault()
      finishVector(true)
    },
    [readOnly, zp, toolMode, finishVector],
  )

  const toolbar = readOnly ? null : (
    <Space.Compact>
      <Button
        type={toolMode === 'draw' ? 'primary' : 'default'}
        onClick={() => {
          setToolMode('draw')
          onSelectRegion(null)
        }}
      >
        绘制
      </Button>
      <Button
        type={toolMode === 'select' ? 'primary' : 'default'}
        icon={<SelectOutlined />}
        onClick={() => {
          setToolMode('select')
          setCurrentVertices([])
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
                  {toolMode === 'draw' && currentVertices.length >= 2 && (
                    <>
                      <Button type="dashed" onClick={() => finishVector(true)}>
                        闭合多边形 ({currentVertices.length} 点)
                      </Button>
                      <Button onClick={() => finishVector(false)}>完成折线</Button>
                    </>
                  )}
                  {toolMode === 'draw' && currentVertices.length > 0 && (
                    <Button icon={<UndoOutlined />} onClick={handleUndoVertex}>
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
                  <Tag>{vecRegions.length} 个向量</Tag>
                </>
              )}
            </Space>
          }
          onStageClick={onStageClick}
          onStageDblClick={onStageDblClick}
          renderContent={({ visibleStrokeWidth }) => (
            <>
              {vecRegions.map((region: Region & { value: VectorValue }, i: number) => (
                <Line
                  key={region.id}
                  id={region.id}
                  points={toFlatPoints(region.value.vertices)}
                  closed={region.value.closed}
                  stroke={labelColor(i)}
                  strokeWidth={visibleStrokeWidth(2)}
                  fill={`${labelColor(i)}30`}
                  onClick={() =>
                    !readOnly && onSelectRegion(selectedRegionId === region.id ? null : region.id)
                  }
                />
              ))}
              {currentVertices.length > 0 && (
                <Line
                  points={toFlatPoints(currentVertices)}
                  stroke="#1890FF"
                  strokeWidth={visibleStrokeWidth(2)}
                  dash={[4, 4]}
                />
              )}
            </>
          )}
        />
      </div>

      {vecRegions.length > 0 && (
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
            dataSource={vecRegions}
            renderItem={(region: Region & { value: VectorValue }, i: number) => (
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
                  <span>
                    {region.label || `${region.value.closed ? '多边形' : '折线'} ${i + 1}`}
                  </span>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {region.value.vertices.length} 点
                  </Typography.Text>
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

      {!readOnly && toolMode === 'draw' && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          点击添加顶点，双击或点「闭合/完成」结束（至少 2 个顶点）。
        </Typography.Text>
      )}
    </div>
  )
}
