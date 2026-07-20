import type { ReactNode } from 'react'
import { Button, Space, Tooltip } from 'antd'
import { DragOutlined, ExpandOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons'
import { Stage, Layer, Image as KonvaImage } from 'react-konva'
import type Konva from 'konva'
import type { VideoStageController } from './useVideoStage'

export interface VideoStageRenderContext {
  videoWidth: number
  videoHeight: number
  stageScale: number
  visibleStrokeWidth: (base?: number) => number
  visibleAnchorSize: (base?: number) => number
  pointerToNatural: VideoStageController['pointerToNatural']
}

type StageMouseHandler = (
  e: Konva.KonvaEventObject<MouseEvent>,
  ctx: VideoStageRenderContext,
) => void

interface VideoStageProps {
  videoEl: HTMLVideoElement | null
  naturalWidth: number
  naturalHeight: number
  controller: VideoStageController
  layerRef: React.MutableRefObject<Konva.Layer | null>
  toolbarExtra?: ReactNode
  renderContent: (ctx: VideoStageRenderContext) => ReactNode
  onStageMouseDown?: StageMouseHandler
  onStageMouseMove?: StageMouseHandler
  onStageMouseUp?: StageMouseHandler
}

/** 视频画布：Konva Stage 以 <video> 为 Image 背景，layerRef 供 rAF 重绘。 */
export default function VideoStage({
  videoEl,
  naturalWidth,
  naturalHeight,
  controller,
  layerRef,
  toolbarExtra,
  renderContent,
  onStageMouseDown,
  onStageMouseMove,
  onStageMouseUp,
}: VideoStageProps) {
  const {
    stageSize,
    stageScale,
    stagePos,
    panMode,
    setPanMode,
    panEffective,
    containerRef,
    stageRef,
    fitToWindow,
    resetZoom,
    zoomBy,
    pointerToNatural,
    visibleStrokeWidth,
    visibleAnchorSize,
    onWheel,
    onStageDragEnd,
  } = controller

  const ctx: VideoStageRenderContext | null =
    naturalWidth && naturalHeight
      ? {
          videoWidth: naturalWidth,
          videoHeight: naturalHeight,
          stageScale,
          visibleStrokeWidth,
          visibleAnchorSize,
          pointerToNatural,
        }
      : null

  const wrap = (handler?: StageMouseHandler) =>
    handler && ctx ? (e: Konva.KonvaEventObject<MouseEvent>) => handler(e, ctx) : undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, minHeight: 0 }}>
      <Space wrap>
        {toolbarExtra}
        <Space.Compact>
          <Tooltip title="放大">
            <Button icon={<ZoomInOutlined />} onClick={() => zoomBy(1.2)} />
          </Tooltip>
          <Tooltip title="缩小">
            <Button icon={<ZoomOutOutlined />} onClick={() => zoomBy(1 / 1.2)} />
          </Tooltip>
          <Tooltip title="适应窗口">
            <Button icon={<ExpandOutlined />} onClick={fitToWindow} />
          </Tooltip>
          <Tooltip title="100% (1:1)">
            <Button onClick={resetZoom}>{Math.round(stageScale * 100)}%</Button>
          </Tooltip>
        </Space.Compact>
        <Tooltip title="平移画布(或按住空格拖拽)">
          <Button
            type={panMode ? 'primary' : 'default'}
            icon={<DragOutlined />}
            onClick={() => setPanMode(!panMode)}
          >
            平移
          </Button>
        </Tooltip>
      </Space>
      <div
        ref={containerRef}
        style={{
          flex: 1,
          minHeight: 300,
          border: '1px solid var(--ant-color-border)',
          borderRadius: 6,
          overflow: 'hidden',
          cursor: panEffective ? 'grab' : 'default',
        }}
      >
        <Stage
          ref={stageRef}
          width={stageSize.width}
          height={stageSize.height}
          scaleX={stageScale}
          scaleY={stageScale}
          x={stagePos.x}
          y={stagePos.y}
          draggable={panEffective}
          onWheel={onWheel}
          onDragEnd={onStageDragEnd}
          onMouseDown={wrap(onStageMouseDown)}
          onMouseMove={wrap(onStageMouseMove)}
          onMouseUp={wrap(onStageMouseUp)}
        >
          <Layer
            ref={(node) => {
              layerRef.current = node
            }}
          >
            {videoEl && naturalWidth > 0 && naturalHeight > 0 && (
              <KonvaImage
                image={videoEl}
                x={0}
                y={0}
                width={naturalWidth}
                height={naturalHeight}
                listening={false}
              />
            )}
            {ctx && renderContent(ctx)}
          </Layer>
        </Stage>
      </div>
    </div>
  )
}
