import { Card, Col, Progress, Row, Statistic } from 'antd'
import { DashboardOutlined, DesktopOutlined, CloudOutlined, HddOutlined } from '@ant-design/icons'
import type { ClusterOverview } from '@/types/monitoring'

interface Props {
  data: ClusterOverview | null
  loading: boolean
}

function getUtilColor(pct: number): string {
  if (pct > 85) return '#ff4d4f'
  if (pct > 60) return '#faad14'
  return '#52c41a'
}

function MetricCard({
  title,
  icon,
  used,
  total,
  unit,
  utilization,
}: {
  title: string
  icon: React.ReactNode
  used: number
  total: number
  unit?: string
  utilization: number
}) {
  const color = getUtilColor(utilization)
  return (
    <Card hoverable>
      <Statistic
        title={title}
        prefix={icon}
        value={used}
        suffix={unit ? ` / ${total} ${unit}` : ''}
      />
      <Progress
        type="dashboard"
        percent={utilization}
        size={80}
        strokeColor={color}
        format={(pct) => `${pct}%`}
        style={{ marginTop: 8 }}
      />
    </Card>
  )
}

export default function ClusterOverviewCards({ data, loading }: Props) {
  if (!data) {
    return (
      <Row gutter={[16, 16]}>
        {[1, 2, 3, 4].map((i) => (
          <Col xs={24} sm={12} lg={6} key={i}>
            <Card loading={loading} />
          </Col>
        ))}
      </Row>
    )
  }

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} lg={6}>
        <MetricCard
          title="GPU"
          icon={<DashboardOutlined />}
          used={data.gpu.used}
          total={data.gpu.total}
          utilization={data.gpu.utilization}
        />
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <MetricCard
          title="CPU 使用率"
          icon={<DesktopOutlined />}
          used={data.cpu.used}
          total={data.cpu.total}
          unit="核"
          utilization={data.cpu.utilization}
        />
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <MetricCard
          title="内存使用率"
          icon={<CloudOutlined />}
          used={data.memory.used}
          total={data.memory.total}
          utilization={data.memory.utilization}
        />
      </Col>
      <Col xs={24} sm={12} lg={6}>
        <Card hoverable>
          <Statistic title="存储使用" prefix={<HddOutlined />} value={data.storage.used} />
        </Card>
      </Col>
    </Row>
  )
}
