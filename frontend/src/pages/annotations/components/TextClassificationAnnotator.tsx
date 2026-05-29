import { useEffect, useState } from 'react'
import { Card, Radio, Space, Spin, Typography } from 'antd'
import type { AnnotationTask, AnnotationProjectDetail } from '@/types/annotation'
import type { AnnotationResultItem } from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'

interface TextClassificationAnnotatorProps {
  task: AnnotationTask
  project: AnnotationProjectDetail
  labels: string[]
  objectConfig?: LabelStudioObjectConfig
  controlConfig?: LabelStudioControlConfig
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
}

export default function TextClassificationAnnotator({
  task,
  labels,
  objectConfig,
  controlConfig,
  onSubmit,
  submitting,
}: TextClassificationAnnotatorProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const textField = objectConfig?.field || 'text'
  const textValue = task.data?.[textField] as string | undefined
  const fileName = (task.data?.kubeaiFileName as string | undefined) || '文本内容'
  const [textContent, setTextContent] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setSelected(null)
    setTextContent(null)
  }, [task.id])

  useEffect(() => {
    if (!textValue) return
    if (!/^https?:\/\//.test(textValue)) {
      setTextContent(textValue)
      return
    }
    let cancelled = false
    setLoading(true)
    fetch(textValue)
      .then((r) => r.text())
      .then((t) => {
        if (!cancelled) setTextContent(t)
      })
      .catch(() => {
        if (!cancelled) setTextContent('文本加载失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [textValue])

  const handleSelect = (label: string) => {
    setSelected(label)
    const result: AnnotationResultItem[] = [
      {
        from_name: controlConfig?.name || 'sentiment',
        to_name: controlConfig?.toName || objectConfig?.name || 'text',
        type: 'choices',
        value: { choices: [label] },
      },
    ]
    onSubmit(result)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div style={{ flex: 1 }}>
        <Card
          style={{ minHeight: 200, maxHeight: 400, overflowY: 'auto' }}
          title={fileName || '文本内容'}
        >
          {loading ? (
            <Spin tip="加载文本中...">
              <div />
            </Spin>
          ) : (
            <Typography.Paragraph
              style={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace', marginBottom: 0 }}
            >
              {textContent || '无文本内容'}
            </Typography.Paragraph>
          )}
        </Card>
      </div>
      <div style={{ width: '100%', maxWidth: 600, margin: '0 auto' }}>
        <Radio.Group value={selected} disabled={submitting} style={{ width: '100%' }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {labels.map((label) => (
              <Radio
                key={label}
                value={label}
                onChange={() => handleSelect(label)}
                style={{ fontSize: 16, padding: '8px 12px' }}
              >
                {label}
              </Radio>
            ))}
          </Space>
        </Radio.Group>
      </div>
    </div>
  )
}
