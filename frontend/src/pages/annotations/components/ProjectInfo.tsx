import { Card, Col, Row, Tag, Progress, Typography } from 'antd'
import type { AnnotationProjectDetail } from '@/types/annotation'

const { Text } = Typography

interface ProjectInfoProps {
  project: AnnotationProjectDetail
}

export default function ProjectInfo({ project }: ProjectInfoProps) {
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
          <Text type="secondary">标注模板</Text>
          <br />
          <Tag color="blue">{project.templateName || '—'}</Tag>
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
