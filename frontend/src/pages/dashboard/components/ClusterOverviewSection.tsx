import { Card, Col, Progress, Row, Statistic } from 'antd'
import { DashboardOutlined, DesktopOutlined, CloudOutlined } from '@ant-design/icons'
import type { ClusterOverviewBrief } from '@/types/dashboard'
import { formatKi } from '@/utils/format'

interface Props {
  data: ClusterOverviewBrief | null
  loading: boolean
}

function getUtilColor(pct: number): string {
  if (pct > 85) return '#ff4d4f'
  if (pct > 60) return '#faad14'
  return '#52c41a'
}

export default function ClusterOverviewSection({ data, loading }: Props) {
  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic
            title="GPU"
            prefix={<DashboardOutlined />}
            value={data?.gpuUsed ?? 0}
            suffix={`/ ${data?.gpuTotal ?? 0}`}
          />
          <Progress
            type="dashboard"
            percent={data?.gpuUtilization ?? 0}
            size={64}
            strokeColor={getUtilColor(data?.gpuUtilization ?? 0)}
            format={(pct) => `${pct}%`}
            style={{ marginTop: 8 }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic
            title="CPU"
            prefix={<DesktopOutlined />}
            value={data?.cpuUsed ?? 0}
            suffix={`/ ${data?.cpuTotal ?? 0} 核`}
          />
          <Progress
            type="dashboard"
            percent={data?.cpuUtilization ?? 0}
            size={64}
            strokeColor={getUtilColor(data?.cpuUtilization ?? 0)}
            format={(pct) => `${pct}%`}
            style={{ marginTop: 8 }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={8}>
        <Card hoverable loading={loading}>
          <Statistic
            title="内存"
            prefix={<CloudOutlined />}
            value={formatKi(data?.memoryUsed ?? 0)}
            suffix={`/ ${formatKi(data?.memoryTotal ?? 0)}`}
          />
          <Progress
            type="dashboard"
            percent={data?.memoryUtilization ?? 0}
            size={64}
            strokeColor={getUtilColor(data?.memoryUtilization ?? 0)}
            format={(pct) => `${pct}%`}
            style={{ marginTop: 8 }}
          />
        </Card>
      </Col>
    </Row>
  )
}
