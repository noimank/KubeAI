import { useEffect, useMemo, useState } from 'react'
import {
  DndContext,
  PointerSensor,
  closestCenter,
  useSensor,
  useSensors,
  type DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  arrayMove,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { Card, Image, Tag, Typography } from 'antd'
import { HolderOutlined } from '@ant-design/icons'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'

interface RankerAnnotatorProps {
  task: AnnotationTask
  objectConfigs: Map<string, LabelStudioObjectConfig>
  controlConfig: LabelStudioControlConfig
  onSubmit: (results: AnnotationResultItem[]) => void
  submitting: boolean
  readOnly: boolean
}

/** 渲染单个待排序项的内容（图片或文本） */
function ItemContent({ item }: { item: unknown }) {
  const img = imageUrlOf(item)
  if (img) {
    return <Image src={img} style={{ maxHeight: 60 }} alt="" />
  }
  return (
    <Typography.Text style={{ wordBreak: 'break-all' }}>
      {typeof item === 'string' ? item : JSON.stringify(item)}
    </Typography.Text>
  )
}

function SortableItem({ id, rank, item }: { id: string; rank: number; item: unknown }) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
  })
  return (
    <div
      ref={setNodeRef}
      style={{
        transform: CSS.Transform.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
        cursor: 'grab',
      }}
      {...attributes}
      {...listeners}
    >
      <Card size="small" style={{ marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
        <HolderOutlined />
        <Tag color="blue">{rank + 1}</Tag>
        <ItemContent item={item} />
      </Card>
    </div>
  )
}

/**
 * Ranker 控件 —— 拖拽排序 List 数据源中的项目（偏好排序 / RLHF）。
 * 全局控件：结果 { order: [原始下标按排名顺序] } 经 onGlobalResult 提交。
 */
export default function RankerAnnotator({
  task,
  objectConfigs,
  controlConfig,
  onSubmit,
  readOnly,
}: RankerAnnotatorProps) {
  const listObject = objectConfigs.get(controlConfig.toName)
  const field = listObject?.field || ''
  const items = useMemo(() => {
    const v = task.data?.[field]
    return Array.isArray(v) ? v : []
  }, [task.data, field])

  // order: 原始下标（字符串）按当前排名顺序
  const [order, setOrder] = useState<string[]>(() => items.map((_, i) => String(i)))

  // 任务变化或数据变化时重置
  useEffect(() => {
    setOrder(items.map((_, i) => String(i)))
  }, [task.id, items])

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  // 排名变化即提交
  useEffect(() => {
    if (order.length === 0) return
    onSubmit([
      {
        from_name: controlConfig.name,
        to_name: controlConfig.toName,
        type: 'ranker',
        value: { order: order.map(Number) },
      },
    ])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [order])

  const onDragEnd = (e: DragEndEvent) => {
    const { active, over } = e
    if (!over || active.id === over.id) return
    setOrder((prev) => {
      const from = prev.indexOf(String(active.id))
      const to = prev.indexOf(String(over.id))
      if (from < 0 || to < 0) return prev
      return arrayMove(prev, from, to)
    })
  }

  if (items.length === 0) {
    return <Typography.Text type="secondary">无待排序项目</Typography.Text>
  }

  return (
    <div style={{ marginBottom: 12 }}>
      <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 6, fontSize: 12 }}>
        {readOnly ? '排序结果（只读）' : '拖拽调整顺序（从上到下 = 最优到最差）'}
      </Typography.Text>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={readOnly ? undefined : onDragEnd}
      >
        <SortableContext items={order} strategy={verticalListSortingStrategy} disabled={readOnly}>
          {order.map((idxStr, rank) => (
            <SortableItem key={idxStr} id={idxStr} rank={rank} item={items[Number(idxStr)]} />
          ))}
        </SortableContext>
      </DndContext>
    </div>
  )
}

function imageUrlOf(item: unknown): string | undefined {
  if (typeof item === 'object' && item !== null) {
    const obj = item as Record<string, unknown>
    const candidate = (obj.image ?? obj.url ?? obj.src) as unknown
    return typeof candidate === 'string' ? candidate : undefined
  }
  return undefined
}
