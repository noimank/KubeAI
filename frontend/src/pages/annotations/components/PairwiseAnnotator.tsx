import { useCallback, useEffect, useState } from 'react'
import { Button, Card, Space, Typography } from 'antd'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import ObjectPreview from './ObjectPreview'

interface PairwiseAnnotatorProps {
  task: AnnotationTask
  /** All object configs in this view (name -> config) */
  objectConfigs: Map<string, LabelStudioObjectConfig>
  controlConfig?: LabelStudioControlConfig
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
  readOnly?: boolean
}

export default function PairwiseAnnotator({
  task,
  objectConfigs,
  controlConfig,
  onSubmit,
  submitting,
  readOnly = false,
}: PairwiseAnnotatorProps) {
  const [selected, setSelected] = useState<'left' | 'right' | null>(null)

  // Parse toName: comma-separated "left,right" → [leftName, rightName]
  const toNames = controlConfig?.toName
    ? controlConfig.toName
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean)
    : []
  const leftName = toNames[0] ?? ''
  const rightName = toNames[1] ?? ''
  const leftConfig = objectConfigs.get(leftName)
  const rightConfig = objectConfigs.get(rightName)
  const leftValue = leftConfig ? (task.data?.[leftConfig.field] as string | undefined) : undefined
  const rightValue = rightConfig
    ? (task.data?.[rightConfig.field] as string | undefined)
    : undefined

  // Reset on task change
  useEffect(() => {
    setSelected(null)
  }, [task.id])

  const submitChoice = useCallback(
    (dir: 'left' | 'right') => {
      const result: AnnotationResultItem = {
        from_name: controlConfig?.name || 'pairwise',
        to_name: controlConfig?.toName || '',
        type: 'pairwise',
        value: { selected: dir },
      }
      onSubmit([result])
    },
    [onSubmit, controlConfig],
  )

  if (!leftName || !rightName || !leftConfig || !rightConfig) {
    return (
      <Card size="small">
        <Typography.Text type="warning">Pairwise 控件需要恰好两个数据标签引用</Typography.Text>
      </Card>
    )
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div style={{ display: 'flex', gap: 12 }}>
        {/* Left */}
        <div
          style={{
            flex: 1,
            cursor: readOnly ? 'default' : 'pointer',
            opacity: selected === 'right' ? 0.5 : 1,
            border: selected === 'left' ? '2px solid #1677ff' : '2px solid transparent',
            borderRadius: 8,
            padding: 4,
            transition: 'all 0.2s',
          }}
          onClick={() => {
            if (readOnly) return
            const next = selected === 'left' ? null : 'left'
            setSelected(next)
            if (next) submitChoice(next)
          }}
        >
          <Typography.Text
            strong
            style={{ display: 'block', textAlign: 'center', marginBottom: 4 }}
          >
            {leftConfig.tag === 'Image' ? '🖼 左' : 'A'}
          </Typography.Text>
          <ObjectPreview objectConfig={leftConfig} value={leftValue} />
        </div>
        {/* Right */}
        <div
          style={{
            flex: 1,
            cursor: readOnly ? 'default' : 'pointer',
            opacity: selected === 'left' ? 0.5 : 1,
            border: selected === 'right' ? '2px solid #1677ff' : '2px solid transparent',
            borderRadius: 8,
            padding: 4,
            transition: 'all 0.2s',
          }}
          onClick={() => {
            if (readOnly) return
            const next = selected === 'right' ? null : 'right'
            setSelected(next)
            if (next) submitChoice(next)
          }}
        >
          <Typography.Text
            strong
            style={{ display: 'block', textAlign: 'center', marginBottom: 4 }}
          >
            {rightConfig.tag === 'Image' ? '🖼 右' : 'B'}
          </Typography.Text>
          <ObjectPreview objectConfig={rightConfig} value={rightValue} />
        </div>
      </div>
      {!readOnly && (
        <Button
          type="primary"
          loading={submitting}
          disabled={!selected}
          onClick={() => selected && submitChoice(selected)}
        >
          提交
        </Button>
      )}
    </Space>
  )
}
