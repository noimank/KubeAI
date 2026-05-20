import { Card, Col, Row, Statistic, Table, Tag, Empty, Button } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getMyAnnotationTasks, getMyAnnotationTaskSummary } from '@/services/annotations'
import type { AnnotationTaskSummary } from '@/types/annotation'

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

interface MyTaskListProps {
  page: number
  pageSize: number
  onPageChange: (page: number, pageSize: number) => void
}

export default function MyTaskList({ page, pageSize, onPageChange }: MyTaskListProps) {
  const navigate = useNavigate()
  const { data: summaryData } = useQuery({
    queryKey: ['myAnnotationTaskSummary'],
    queryFn: getMyAnnotationTaskSummary,
  })

  const { data: tasksData, isLoading } = useQuery({
    queryKey: ['myAnnotationTasks', page, pageSize],
    queryFn: () => getMyAnnotationTasks({ current: page, pageSize }),
  })

  const totalAssigned =
    summaryData?.reduce((sum: number, s: AnnotationTaskSummary) => sum + s.assignedTasks, 0) ?? 0
  const totalCompleted =
    summaryData?.reduce((sum: number, s: AnnotationTaskSummary) => sum + s.completedTasks, 0) ?? 0
  const totalTasks =
    summaryData?.reduce((sum: number, s: AnnotationTaskSummary) => sum + s.totalTasks, 0) ?? 0

  return (
    <div>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card>
            <Statistic title="待完成" value={totalAssigned} valueStyle={{ color: '#1677ff' }} />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic
              title="进行中"
              value={totalTasks - totalAssigned - totalCompleted}
              valueStyle={{ color: '#faad14' }}
            />
          </Card>
        </Col>
        <Col span={8}>
          <Card>
            <Statistic title="已完成" value={totalCompleted} valueStyle={{ color: '#52c41a' }} />
          </Card>
        </Col>
      </Row>

      <Table
        rowKey="id"
        dataSource={tasksData?.items}
        loading={isLoading}
        pagination={{
          current: page,
          pageSize,
          total: tasksData?.total ?? 0,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: onPageChange,
        }}
        locale={{ emptyText: <Empty description="暂无分配的标注任务" /> }}
        columns={[
          {
            title: '项目名称',
            dataIndex: 'projectName',
            render: (name: string, record) => (
              <Link to={`/annotations/${record.projectId}`}>{name || '-'}</Link>
            ),
          },
          {
            title: '标注类型',
            dataIndex: 'annotationType',
            width: 120,
            render: (type: string) => {
              const info = ANNOTATION_TYPE_MAP[type] || { label: type, color: 'default' }
              return <Tag color={info.color}>{info.label}</Tag>
            },
          },
          {
            title: '状态',
            dataIndex: 'status',
            width: 100,
            render: (status: string) => {
              const statusMap: Record<string, { label: string; color: string }> = {
                assigned: { label: '待开始', color: 'processing' },
                in_progress: { label: '进行中', color: 'blue' },
                completed: { label: '已完成', color: 'success' },
              }
              const info = statusMap[status] || { label: status, color: 'default' }
              return <Tag color={info.color}>{info.label}</Tag>
            },
          },
          {
            title: '分配时间',
            dataIndex: 'updatedAt',
            width: 180,
          },
          {
            title: '操作',
            width: 120,
            render: (_: unknown, record) =>
              record.status === 'assigned' || record.status === 'in_progress' ? (
                <Button
                  type="link"
                  size="small"
                  onClick={() => navigate(`/annotations/projects/${record.projectId}/workspace`)}
                >
                  开始标注
                </Button>
              ) : null,
          },
        ]}
      />
    </div>
  )
}
