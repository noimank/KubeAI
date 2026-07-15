import type { ReactNode } from 'react'
import { Button, Space, Tooltip } from 'antd'
import { DragOutlined, ExpandOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons'
import { Stage, Layer, Image as KonvaImage } from 'react-konva'
import type Konva from 'konva'
import type { ZoomPanController } from './useZoomPan'

export interface StageRenderContext {
  image: HTMLImageElement
  stageScale: number
  visibleStrokeWidth: (base?: number) => number
  visibleAnchorSize: (base?: number) => number
  pointerToImage: ZoomPanController['pointerToImage']
}

interface StageMouseHandler {
  (e: Konva.KonvaEventObject<MouseEvent>, ctx: StageRenderContext): void
}

interface ZoomPanImageStageProps {
  controller: ZoomPanController
  /** 额外的工具栏内容(绘制/选择/删除等业务按钮) */
  toolbarExtra?: ReactNode
  /** 注入形状树,由消费者渲染 Rect/Line/Circle 等 */
  renderContent: (ctx: StageRenderContext) => ReactNode
  onStageMouseDown?: StageMouseHandler
  onStageMouseMove?: StageMouseHandler
  onStageMouseUp?: StageMouseHandler
  onStageClick?: StageMouseHandler
  onStageDblClick?: StageMouseHandler
}

export default function ZoomPanImageStage({
  controller,
  toolbarExtra,
  renderContent,
  onStageMouseDown,
  onStageMouseMove,
  onStageMouseUp,
  onStageClick,
  onStageDblClick,
}: ZoomPanImageStageProps) {
  const {
    image,
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
    pointerToImage,
    visibleStrokeWidth,
    visibleAnchorSize,
    onWheel,
    onStageDragEnd,
  } = controller

  const ctx: StageRenderContext | null = image
    ? { image, stageScale, visibleStrokeWidth, visibleAnchorSize, pointerToImage }
    : null

  const wrap = (handler?: StageMouseHandler) =>
    handler && ctx ? (e: Konva.KonvaEventObject<MouseEvent>) => handler(e, ctx) : undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, height: '100%' }}>
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
          minHeight: 400,
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
          onClick={wrap(onStageClick)}
          onDblClick={wrap(onStageDblClick)}
        >
          <Layer>
            {image && <KonvaImage image={image} listening={false} />}
            {ctx && renderContent(ctx)}
          </Layer>
        </Stage>
      </div>
    </div>
  )
}
