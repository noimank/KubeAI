import { Card, Col, Row, Statistic } from 'antd'
import { DashboardOutlined, RocketOutlined, DatabaseOutlined } from '@ant-design/icons'
import type { DashboardResourceOverview } from '@/types/dashboard'

interface Props {
  data: DashboardResourceOverview | null
  loading: boolean
}

export default function ResourceOverviewCards({ data, loading }: Props) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic
            title="GPU 使用"
            prefix={<DashboardOutlined />}
            value={data?.gpuUsed ?? 0}
            suffix={`/ ${data?.gpuTotal ?? 0}`}
          />
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic title="运行中任务" prefix={<RocketOutlined />} value={data?.activeJobs ?? 0} />
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic
            title="活跃数据集"
            prefix={<DatabaseOutlined />}
            value={data?.activeDatasets ?? 0}
          />
        </Card>
      </Col>
    </Row>
  )
}
