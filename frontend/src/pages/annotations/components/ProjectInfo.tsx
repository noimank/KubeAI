import { Card, Col, Row, Tag, Progress, Typography } from 'antd'
import type { AnnotationProjectDetail } from '@/types/annotation'

const { Text } = Typography

interface ProjectInfoProps {
  project: AnnotationProjectDetail
}

const STATUS_CONFIG: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  pending: { label: '初始化中', color: 'blue' },
  active: { label: '活跃', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
  archived: { label: '已归档', color: 'warning' },
}

export default function ProjectInfo({ project }: ProjectInfoProps) {
  const statusInfo = STATUS_CONFIG[project.status] || { label: project.status, color: 'default' }
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
        <Col>
          <Text type="secondary">状态</Text>
          <br />
          <Tag color={statusInfo.color}>{statusInfo.label}</Tag>
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
