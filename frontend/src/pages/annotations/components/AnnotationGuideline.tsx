import { Card, Tag, Typography, Button } from 'antd'
import { DoubleRightOutlined, DoubleLeftOutlined } from '@ant-design/icons'
import type { AnnotationProjectDetail } from '@/types/annotation'

const TYPE_LABELS: Record<string, string> = {
  image_classification: '图像分类',
  object_detection: '目标检测',
  image_segmentation: '图像分割',
  text_classification: '文本分类',
}

interface AnnotationGuidelineProps {
  project: AnnotationProjectDetail
  labels: string[]
  collapsed: boolean
  onToggle: () => void
}

export default function AnnotationGuideline({
  project,
  labels,
  collapsed,
  onToggle,
}: AnnotationGuidelineProps) {
  if (collapsed) {
    return (
      <div
        style={{
          width: 40,
          borderLeft: '1px solid var(--ant-color-border)',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          paddingTop: 12,
        }}
      >
        <Button type="text" size="small" icon={<DoubleLeftOutlined />} onClick={onToggle} />
      </div>
    )
  }

  return (
    <div
      style={{
        width: 300,
        borderLeft: '1px solid var(--ant-color-border)',
        padding: 16,
        overflowY: 'auto',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 12,
        }}
      >
        <Typography.Text strong>标注规范</Typography.Text>
        <Button type="text" size="small" icon={<DoubleRightOutlined />} onClick={onToggle} />
      </div>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Typography.Text type="secondary">标注类型</Typography.Text>
        <div style={{ marginTop: 4 }}>
          <Tag color="blue">{TYPE_LABELS[project.annotationType] || project.annotationType}</Tag>
        </div>
      </Card>

      {project.description && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary">标注指引</Typography.Text>
          <Typography.Paragraph
            style={{ marginTop: 4, marginBottom: 0 }}
            ellipsis={{ rows: 8, expandable: true, symbol: '展开' }}
          >
            {project.description}
          </Typography.Paragraph>
        </Card>
      )}

      {project.labelingTemplateDescription && (
        <Card size="small" style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary">模板说明</Typography.Text>
          <Typography.Paragraph style={{ marginTop: 4, marginBottom: 0 }}>
            {project.labelingTemplateDescription}
          </Typography.Paragraph>
        </Card>
      )}

      <Card size="small">
        <Typography.Text type="secondary">标签列表</Typography.Text>
        <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {labels.map((label) => (
            <Tag key={label}>{label}</Tag>
          ))}
        </div>
      </Card>
    </div>
  )
}
