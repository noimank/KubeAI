import { Card, Image, Typography } from 'antd'
import type { LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import { appendAuthToken } from '@/utils/constants'

interface ObjectPreviewProps {
  objectConfig?: LabelStudioObjectConfig
  value?: string
}

/** Shared object data preview — Image/Audio/Video/Text/HyperText */
export default function ObjectPreview({ objectConfig, value }: ObjectPreviewProps) {
  if (!value) {
    const tagName = objectConfig?.tag ?? null
    const labelMap: Record<string, string> = {
      Audio: '🎵 音频数据',
      Video: '🎬 视频数据',
      Chat: '💬 对话数据',
      Paragraphs: '📝 段落数据',
      TimeSeries: '📈 时间序列数据',
      Table: '📊 表格数据',
    }
    return (
      <Card size="small">
        <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
          {labelMap[tagName ?? ''] ?? '无内容'}
        </Typography.Paragraph>
      </Card>
    )
  }

  if (objectConfig?.tag === 'Image') {
    return (
      <div style={{ textAlign: 'center' }}>
        <Image src={appendAuthToken(value)} style={{ maxHeight: 160 }} />
      </div>
    )
  }

  if (objectConfig?.tag === 'Audio') {
    return <audio src={appendAuthToken(value)} controls style={{ width: '100%' }} />
  }

  if (objectConfig?.tag === 'Video') {
    return <video src={appendAuthToken(value)} controls style={{ width: '100%', maxHeight: 200 }} />
  }

  if (objectConfig?.tag === 'PDF' || objectConfig?.tag === 'Pdf') {
    return (
      <Card size="small">
        <Typography.Text type="secondary">📕 PDF 文档</Typography.Text>
      </Card>
    )
  }

  return (
    <Card size="small">
      <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
        {value}
      </Typography.Paragraph>
    </Card>
  )
}
