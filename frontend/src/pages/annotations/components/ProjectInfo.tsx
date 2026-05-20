import { Card, Col, Row, Tag, Progress, Typography } from 'antd'
import type { AnnotationProjectDetail } from '@/types/annotation'

const { Text } = Typography

const ANNOTATION_TYPE_MAP: Record<string, { label: string; color: string }> = {
  image_classification: { label: '图像分类', color: 'blue' },
  object_detection: { label: '目标检测', color: 'green' },
  image_segmentation: { label: '图像分割', color: 'purple' },
  text_classification: { label: '文本分类', color: 'orange' },
  choices: { label: '分类选择', color: 'blue' },
  rectanglelabels: { label: '矩形框', color: 'green' },
  polygonlabels: { label: '多边形', color: 'purple' },
  textarea: { label: '文本填写', color: 'orange' },
  rating: { label: '评分', color: 'gold' },
}

interface ProjectInfoProps {
  project: AnnotationProjectDetail
}

export default function ProjectInfo({ project }: ProjectInfoProps) {
  const typeInfo = ANNOTATION_TYPE_MAP[project.annotationType] || {
    label: project.annotationType,
    color: 'default',
  }

  return (
    <Card style={{ marginBottom: 16 }}>
      <Row gutter={[24, 12]} align="middle">
        <Col>
          <Text type="secondary">数据集</Text>
          <br />
          <Text strong>
            {project.datasetName}
            {project.datasetVersionNumber ? ` v${project.datasetVersionNumber}` : ''}
          </Text>
        </Col>
        <Col>
          <Text type="secondary">标注类型</Text>
          <br />
          <Tag color={typeInfo.color}>{typeInfo.label}</Tag>
        </Col>
        <Col flex="auto">
          <Text type="secondary">进度</Text>
          <br />
          <Progress
            percent={project.progressPercent}
            size="small"
            style={{ maxWidth: 240 }}
            format={() => `${project.completedTasks}/${project.totalTasks}`}
          />
        </Col>
      </Row>
    </Card>
  )
}
