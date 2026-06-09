import { useEffect, useState } from 'react'
import { Button, Card, Image, Input, Space, Typography } from 'antd'
import type {
  AnnotationProjectDetail,
  AnnotationResultItem,
  AnnotationTask,
} from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import { appendAuthToken } from '@/utils/constants'

interface TextAreaAnnotatorProps {
  task: AnnotationTask
  project: AnnotationProjectDetail
  labels: string[]
  objectConfig?: LabelStudioObjectConfig
  controlConfig?: LabelStudioControlConfig
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
}

export default function TextAreaAnnotator({
  task,
  objectConfig,
  controlConfig,
  onSubmit,
  submitting,
}: TextAreaAnnotatorProps) {
  const [value, setValue] = useState('')
  const objectValue = objectConfig
    ? (task.data?.[objectConfig.field] as string | undefined)
    : undefined

  useEffect(() => {
    setValue('')
  }, [task.id])

  const handleSubmit = () => {
    onSubmit([
      {
        from_name: controlConfig?.name || 'answer',
        to_name: controlConfig?.toName || objectConfig?.name || 'text',
        type: 'textarea',
        value: { text: [value] },
      },
    ])
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card size="small">
        {objectConfig?.tag === 'Image' && objectValue ? (
          <Image src={appendAuthToken(objectValue)} style={{ maxHeight: 520 }} />
        ) : (
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
            {objectValue || '无内容'}
          </Typography.Paragraph>
        )}
      </Card>
      <Input.TextArea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        rows={8}
        placeholder="请输入标注内容"
      />
      <Button type="primary" onClick={handleSubmit} loading={submitting} disabled={!value.trim()}>
        提交
      </Button>
    </Space>
  )
}
