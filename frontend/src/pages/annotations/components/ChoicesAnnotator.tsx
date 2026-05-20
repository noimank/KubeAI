import { useEffect, useState } from 'react'
import { Button, Card, Checkbox, Image, Radio, Space, Typography } from 'antd'
import type {
  AnnotationProjectDetail,
  AnnotationResultItem,
  AnnotationTask,
} from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'

interface ChoicesAnnotatorProps {
  task: AnnotationTask
  project: AnnotationProjectDetail
  labels: string[]
  objectConfig?: LabelStudioObjectConfig
  controlConfig?: LabelStudioControlConfig
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
}

export default function ChoicesAnnotator({
  task,
  labels,
  objectConfig,
  controlConfig,
  onSubmit,
  submitting,
}: ChoicesAnnotatorProps) {
  const [selected, setSelected] = useState<string[]>([])
  const objectValue = objectConfig
    ? (task.data?.[objectConfig.field] as string | undefined)
    : undefined
  const multiple = controlConfig?.choice?.includes('multiple')

  useEffect(() => {
    setSelected([])
  }, [task.id])

  const submitChoices = (choices: string[]) => {
    onSubmit([
      {
        from_name: controlConfig?.name || 'choice',
        to_name: controlConfig?.toName || objectConfig?.name || 'data',
        type: 'choices',
        value: { choices },
      },
    ])
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <ObjectPreview objectConfig={objectConfig} value={objectValue} />
      {multiple ? (
        <>
          <Checkbox.Group
            value={selected}
            disabled={submitting}
            onChange={(values) => setSelected(values as string[])}
          >
            <Space direction="vertical">
              {labels.map((label) => (
                <Checkbox key={label} value={label}>
                  {label}
                </Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
          <Button
            type="primary"
            loading={submitting}
            disabled={selected.length === 0}
            onClick={() => submitChoices(selected)}
          >
            提交
          </Button>
        </>
      ) : (
        <Radio.Group
          value={selected[0]}
          disabled={submitting}
          onChange={(event) => {
            const value = event.target.value
            setSelected([value])
            submitChoices([value])
          }}
        >
          <Space direction="vertical">
            {labels.map((label) => (
              <Radio key={label} value={label}>
                {label}
              </Radio>
            ))}
          </Space>
        </Radio.Group>
      )}
    </Space>
  )
}

function ObjectPreview({
  objectConfig,
  value,
}: {
  objectConfig?: LabelStudioObjectConfig
  value?: string
}) {
  if (objectConfig?.tag === 'Image' && value) {
    return (
      <div style={{ textAlign: 'center' }}>
        <Image src={value} style={{ maxHeight: 520 }} />
      </div>
    )
  }
  if (objectConfig?.tag === 'Audio' && value)
    return <audio src={value} controls style={{ width: '100%' }} />
  if (objectConfig?.tag === 'Video' && value)
    return <video src={value} controls style={{ width: '100%' }} />

  return (
    <Card size="small">
      <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
        {value || '无内容'}
      </Typography.Paragraph>
    </Card>
  )
}
