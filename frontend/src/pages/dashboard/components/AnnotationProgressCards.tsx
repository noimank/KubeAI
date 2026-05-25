import { Card, Col, Row, Statistic } from 'antd'
import { EditOutlined, CheckCircleOutlined, PieChartOutlined } from '@ant-design/icons'
import type { AnnotationProgressOverview } from '@/types/dashboard'

interface Props {
  data: AnnotationProgressOverview | null
  loading: boolean
}

export default function AnnotationProgressCards({ data, loading }: Props) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic title="待办任务" prefix={<EditOutlined />} value={data?.pendingCount ?? 0} />
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic
            title="今日完成"
            prefix={<CheckCircleOutlined />}
            value={data?.todayCompleted ?? 0}
          />
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic
            title="总完成率"
            prefix={<PieChartOutlined />}
            value={data?.totalCompletionRate ?? 0}
            suffix="%"
            precision={1}
          />
        </Card>
      </Col>
    </Row>
  )
}
