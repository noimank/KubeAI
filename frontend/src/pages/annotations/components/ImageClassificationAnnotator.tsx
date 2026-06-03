import { useEffect, useState } from 'react'
import { Image, Radio, Space, Spin } from 'antd'
import type { AnnotationTask, AnnotationProjectDetail } from '@/types/annotation'
import type { AnnotationResultItem } from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import { appendAuthToken } from '@/utils/constants'

interface ImageClassificationAnnotatorProps {
  task: AnnotationTask
  project: AnnotationProjectDetail
  labels: string[]
  objectConfig?: LabelStudioObjectConfig
  controlConfig?: LabelStudioControlConfig
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
}

export default function ImageClassificationAnnotator({
  task,
  labels,
  objectConfig,
  controlConfig,
  onSubmit,
  submitting,
}: ImageClassificationAnnotatorProps) {
  const [selected, setSelected] = useState<string | null>(null)
  const imageField = objectConfig?.field || 'image'
  const imageUrl = task.data?.[imageField] as string | undefined

  useEffect(() => {
    setSelected(null)
  }, [task.id])

  const handleSelect = (label: string) => {
    setSelected(label)
    const result: AnnotationResultItem[] = [
      {
        from_name: controlConfig?.name || 'choice',
        to_name: controlConfig?.toName || objectConfig?.name || 'image',
        type: 'choices',
        value: { choices: [label] },
      },
    ]
    onSubmit(result)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
      <div
        style={{
          flex: 1,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: 300,
        }}
      >
        {imageUrl ? (
          <Image
            src={appendAuthToken(imageUrl)}
            style={{ maxWidth: '100%', maxHeight: 500 }}
            preview={false}
          />
        ) : (
          <Spin tip="加载图片中...">
            <div />
          </Spin>
        )}
      </div>
      <div style={{ width: '100%', maxWidth: 600 }}>
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
