import { useCallback, useEffect, useMemo, useState } from 'react'
import { Button, List, Popconfirm, Space, Tag, Typography } from 'antd'
import { DeleteOutlined, DragOutlined, PlusOutlined, SelectOutlined } from '@ant-design/icons'
import { Rect } from 'react-konva'
import type Konva from 'konva'
import { getMessageInstance } from '@/utils/messageHolder'
import { labelColor } from '../annotationColors'
import LabelPalette from '../LabelPalette'
import { regionsOf } from '../../utils/regions'
import type { Region, RegionUpdate } from '../../hooks/useAnnotationRegions'
import type { LabelStudioControlConfig } from '../../utils/parseLabelConfig'
import type { VideoStageController } from './useVideoStage'
import VideoStage, { type VideoStageRenderContext } from './VideoStage'
import { useVideoPlayerContext } from './VideoPlayerContext'
import { getShapeAtFrame } from './videoMath'
import type { VideoKeyframe } from '../../hooks/useAnnotationRegions'

interface VideoRectangleLayerProps {
  controlConfig: LabelStudioControlConfig
  regions: Region[]
  selectedRegionId: string | null
  readOnly: boolean
  rectLabels: string[]
  videoEl: HTMLVideoElement | null
  stageController: VideoStageController
  layerRef: React.MutableRefObject<Konva.Layer | null>
  onAddRegion: (region: Region) => void
  onUpdateRegion: (id: string, updates: RegionUpdate) => void
  onDeleteRegion: (id: string) => void
  onSelectRegion: (id: string | null) => void
}

type ToolMode = 'select' | 'draw'

interface DrawRect {
  x: number
  y: number
  w: number
  h: number
} // 百分比坐标

const MIN_SIZE_PCT = 1

function pxToPct(px: number, dim: number): number {
  return dim > 0 ? (px / dim) * 100 : 0
}
function pctToPx(pct: number, dim: number): number {
  return (pct / 100) * dim
}

/**
 * VideoRectangle 标注层 —— 在视频画布上画框跟踪目标。
 *
 * 画框 → 当前帧创建单关键帧 sequence；播放时 getShapeAtFrame 插值显示；
 * 拖动框或点「添加关键帧」在当前帧烙印关键帧（手动跟踪工作流）。
 * 坐标全程百分比（LS 规范），边界处与视频像素互转。label 来自外部 <Labels>。
 */
export default function VideoRectangleLayer({
  controlConfig,
  regions,
  selectedRegionId,
  readOnly,
  rectLabels,
  videoEl,
  stageController,
  layerRef,
  onAddRegion,
  onUpdateRegion,
  onDeleteRegion,
  onSelectRegion,
}: VideoRectangleLayerProps) {
  const player = useVideoPlayerContext()
  const { currentFrame, videoWidth, videoHeight } = player

  const [toolMode, setToolMode] = useState<ToolMode>('draw')
  const [activeLabel, setActiveLabel] = useState<string | null>(rectLabels[0] ?? null)
  const [drawing, setDrawing] = useState<DrawRect | null>(null)

  useEffect(() => {
    setToolMode('draw')
    setDrawing(null)
    setActiveLabel(rectLabels[0] ?? null)
  }, [rectLabels])

  const rectRegions = useMemo(
    () => regionsOf(regions, controlConfig.name, 'videorectangle'),
    [regions, controlConfig.name],
  )

  /** 在当前帧烙印关键帧（替换同帧关键帧，保持排序） */
  const pinKeyframe = useCallback(
    (
      regionId: string,
      shape: { x: number; y: number; width: number; height: number; rotation: number },
    ) => {
      const region = rectRegions.find((r) => r.id === regionId)
      if (!region) return
      const seq: VideoKeyframe[] = region.value.sequence
        .filter((kf) => kf.frame !== currentFrame)
        .concat([{ frame: currentFrame, enabled: true, ...shape }])
        .sort((a, b) => a.frame - b.frame)
      onUpdateRegion(regionId, { value: { kind: 'videorectangle', sequence: seq } })
    },
    [rectRegions, currentFrame, onUpdateRegion],
  )

  const onStageMouseDown = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent>, ctx: VideoStageRenderContext) => {
      if (readOnly || stageController.panEffective || toolMode !== 'draw') return
      if (e.evt.button !== 0) return
      if (e.target !== e.target.getStage()) return
      const p = ctx.pointerToNatural()
      if (!p) return
      setDrawing({ x: pxToPct(p.x, videoWidth), y: pxToPct(p.y, videoHeight), w: 0, h: 0 })
    },
    [readOnly, stageController, toolMode, videoWidth, videoHeight],
  )

  const onStageMouseMove = useCallback(
    (_e: Konva.KonvaEventObject<MouseEvent>, ctx: VideoStageRenderContext) => {
      if (!drawing) return
      const p = ctx.pointerToNatural()
      if (!p) return
      setDrawing((prev) =>
        prev
          ? { ...prev, w: pxToPct(p.x, videoWidth) - prev.x, h: pxToPct(p.y, videoHeight) - prev.y }
          : null,
      )
    },
    [drawing, videoWidth, videoHeight],
  )

  const onStageMouseUp = useCallback(() => {
    if (!drawing) return
    const { x, y, w, h } = drawing
    setDrawing(null)
    if (Math.abs(w) < MIN_SIZE_PCT || Math.abs(h) < MIN_SIZE_PCT) return
    if (rectLabels.length > 0 && !activeLabel) {
      getMessageInstance()?.warning('请先选择标签')
      return
    }
    onAddRegion({
      id: crypto.randomUUID(),
      fromName: controlConfig.name,
      label: activeLabel ?? undefined,
      value: {
        kind: 'videorectangle',
        sequence: [
          {
            frame: currentFrame,
            enabled: true,
            x: w < 0 ? x + w : x,
            y: h < 0 ? y + h : y,
            width: Math.abs(w),
            height: Math.abs(h),
            rotation: 0,
          },
        ],
      },
      perRegionResults: {},
    })
  }, [drawing, rectLabels.length, activeLabel, controlConfig.name, currentFrame, onAddRegion])

  // 选中 region 当前帧的插值形状（用于「添加关键帧」烙印当前位置）
  const selectedRegion = rectRegions.find((r) => r.id === selectedRegionId) ?? null
  const selectedShape = selectedRegion
    ? getShapeAtFrame(selectedRegion.value.sequence, currentFrame)
    : null

  const handleAddKeyframe = useCallback(() => {
    if (!selectedRegion || !selectedShape) return
    pinKeyframe(selectedRegion.id, {
      x: selectedShape.x,
      y: selectedShape.y,
      width: selectedShape.width,
      height: selectedShape.height,
      rotation: selectedShape.rotation,
    })
  }, [selectedRegion, selectedShape, pinKeyframe])

  const toolbarExtra = readOnly ? (
    <Tag>{rectRegions.length} 个框</Tag>
  ) : (
    <Space>
      <Space.Compact>
        <Button
          type={toolMode === 'draw' ? 'primary' : 'default'}
          icon={<DragOutlined />}
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
          onClick={() => setToolMode('select')}
        >
          选择
        </Button>
      </Space.Compact>
      <Button
        icon={<PlusOutlined />}
        disabled={!selectedRegion}
        onClick={handleAddKeyframe}
        title="在当前帧为选中框烙印关键帧（手动跟踪）"
      >
        添加关键帧 (帧 {currentFrame})
      </Button>
      <Popconfirm
        title="确认删除选中的框？"
        onConfirm={() => selectedRegionId && onDeleteRegion(selectedRegionId)}
        disabled={!selectedRegionId}
      >
        <Button icon={<DeleteOutlined />} disabled={!selectedRegionId}>
          删除选中
        </Button>
      </Popconfirm>
      <Tag>{rectRegions.length} 个框</Tag>
    </Space>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, minHeight: 0 }}>
      {!readOnly && rectLabels.length > 0 && (
        <LabelPalette labels={rectLabels} activeLabel={activeLabel} onChange={setActiveLabel} />
      )}
      <VideoStage
        videoEl={videoEl}
        naturalWidth={videoWidth}
        naturalHeight={videoHeight}
        controller={stageController}
        layerRef={layerRef}
        toolbarExtra={toolbarExtra}
        onStageMouseDown={onStageMouseDown}
        onStageMouseMove={onStageMouseMove}
        onStageMouseUp={onStageMouseUp}
        renderContent={(ctx: VideoStageRenderContext) => (
          <>
            {rectRegions.map((region, i) => {
              const shape = getShapeAtFrame(region.value.sequence, currentFrame)
              if (!shape) return null
              const isSelected = region.id === selectedRegionId
              return (
                <Rect
                  key={region.id}
                  id={region.id}
                  x={pctToPx(shape.x, ctx.videoWidth)}
                  y={pctToPx(shape.y, ctx.videoHeight)}
                  width={pctToPx(shape.width, ctx.videoWidth)}
                  height={pctToPx(shape.height, ctx.videoHeight)}
                  rotation={shape.rotation}
                  stroke={labelColor(i)}
                  strokeWidth={ctx.visibleStrokeWidth(isSelected ? 3 : 2)}
                  fill={`${labelColor(i)}20`}
                  draggable={!readOnly && toolMode === 'select' && !stageController.panEffective}
                  onClick={() => !readOnly && onSelectRegion(isSelected ? null : region.id)}
                  onDragEnd={(e: Konva.KonvaEventObject<DragEvent>) => {
                    const node = e.target
                    pinKeyframe(region.id, {
                      x: pxToPct(node.x(), ctx.videoWidth),
                      y: pxToPct(node.y(), ctx.videoHeight),
                      width: shape.width,
                      height: shape.height,
                      rotation: shape.rotation,
                    })
                    node.position({
                      x: pctToPx(shape.x, ctx.videoWidth),
                      y: pctToPx(shape.y, ctx.videoHeight),
                    })
                  }}
                />
              )
            })}
            {drawing && (
              <Rect
                x={pctToPx(drawing.w < 0 ? drawing.x + drawing.w : drawing.x, ctx.videoWidth)}
                y={pctToPx(drawing.h < 0 ? drawing.y + drawing.h : drawing.y, ctx.videoHeight)}
                width={pctToPx(Math.abs(drawing.w), ctx.videoWidth)}
                height={pctToPx(Math.abs(drawing.h), ctx.videoHeight)}
                stroke="#1677FF"
                strokeWidth={ctx.visibleStrokeWidth(2)}
                dash={[4, 4]}
              />
            )}
          </>
        )}
      />
      {rectRegions.length > 0 && (
        <div
          style={{
            maxHeight: 120,
            overflowY: 'auto',
            background: 'var(--ant-color-bg-container)',
            border: '1px solid var(--ant-color-border)',
            borderRadius: 6,
          }}
        >
          <List
            size="small"
            dataSource={rectRegions}
            renderItem={(region, i) => (
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
                  <span>{region.label || `框 ${i + 1}`}</span>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {region.value.sequence.length} 关键帧
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
    </div>
  )
}
