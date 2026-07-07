import { Card, Table, Progress, Tag, Row, Col, Button } from 'antd'

interface ResultAlgorithm {
  name: string
  runtimePref: string
  time: string
}

interface ResultDevice {
  name: string
  maxCapacity: number
  minOperatingLoad: number
  total: number
  objects: { name: string; amount: number }[]
}

interface ResultManipulatedObject {
  name: string
  totalAvailable: number
  totalAllocated: number
  usageRate: number
}

export interface ResourceAllocationResultData {
  algorithm: ResultAlgorithm
  status: string
  objective: string
  solutionInfo: {
    devices: ResultDevice[]
    manipulatedObjects: ResultManipulatedObject[]
  }
}

interface Props {
  resultData: ResourceAllocationResultData
  onReset: () => void
}

const statusEnum: Record<string, string> = {
  Optimal: '最优解',
  Feasible: '可行解',
  Infeasible: '无解',
}

const runtimePrefEnum: Record<string, string> = {
  balanced: '平衡',
  speed: '速度优先',
  precision: '精度优先',
}

const getProgressColor = (percentage: number) => {
  if (percentage >= 90) return '#FF4D4F'
  if (percentage >= 70) return '#FAAD14'
  return '#52C41A'
}

export default function ResourceAllocationResult({ resultData, onReset }: Props) {
  const { algorithm, status, objective, solutionInfo } = resultData
  const devices = solutionInfo?.devices || []
  const manipulatedObjects = solutionInfo?.manipulatedObjects || []

  const calculateLoadRate = (device: ResultDevice) => {
    if (!device?.maxCapacity) return 0
    return Number(((Number(device.total || 0) / Number(device.maxCapacity)) * 100).toFixed(2))
  }

  const calculatePercentage = (allocated: number, available: number) => {
    if (!available) return 0
    return Number(((Number(allocated || 0) / Number(available)) * 100).toFixed(2))
  }

  return (
    <div style={{ padding: 24, maxWidth: 1200, margin: '0 auto' }}>
      <h2 style={{ textAlign: 'center', fontSize: 24, fontWeight: 600, marginBottom: 24 }}>
        设备-优化对象优化结果
      </h2>

      <Card style={{ marginBottom: 24 }}>
        <h3
          style={{
            fontSize: 16,
            fontWeight: 600,
            marginBottom: 20,
            paddingBottom: 10,
            borderBottom: '1px solid var(--ant-color-border)',
          }}
        >
          1. 算法与核心指标
        </h3>
        <Row gutter={20}>
          <Col span={5}>
            <div style={{ marginBottom: 12 }}>
              <div
                style={{ fontSize: 14, color: 'var(--ant-color-text-tertiary)', marginBottom: 4 }}
              >
                算法
              </div>
              <div style={{ fontSize: 16, fontWeight: 500 }}>{algorithm?.name}</div>
            </div>
          </Col>
          <Col span={5}>
            <div style={{ marginBottom: 12 }}>
              <div
                style={{ fontSize: 14, color: 'var(--ant-color-text-tertiary)', marginBottom: 4 }}
              >
                运行偏好
              </div>
              <div style={{ fontSize: 16, fontWeight: 500 }}>
                {runtimePrefEnum[algorithm?.runtimePref] || algorithm?.runtimePref}
              </div>
            </div>
          </Col>
          <Col span={5}>
            <div style={{ marginBottom: 12 }}>
              <div
                style={{ fontSize: 14, color: 'var(--ant-color-text-tertiary)', marginBottom: 4 }}
              >
                目标值（总成本/元）
              </div>
              <div style={{ fontSize: 16, fontWeight: 500 }}>{objective || '0.00'}</div>
            </div>
          </Col>
          <Col span={5}>
            <div style={{ marginBottom: 12 }}>
              <div
                style={{ fontSize: 14, color: 'var(--ant-color-text-tertiary)', marginBottom: 4 }}
              >
                可行性状态
              </div>
              <div>
                <Tag color={status === 'Optimal' || status === 'Feasible' ? 'success' : 'error'}>
                  {statusEnum[status] || status}
                </Tag>
              </div>
            </div>
          </Col>
          <Col span={4}>
            <div style={{ marginBottom: 12 }}>
              <div
                style={{ fontSize: 14, color: 'var(--ant-color-text-tertiary)', marginBottom: 4 }}
              >
                计算用时(秒)
              </div>
              <div style={{ fontSize: 16, fontWeight: 500 }}>{algorithm?.time}</div>
            </div>
          </Col>
        </Row>
      </Card>

      <Card style={{ marginBottom: 24 }}>
        <h3
          style={{
            fontSize: 16,
            fontWeight: 600,
            marginBottom: 20,
            paddingBottom: 10,
            borderBottom: '1px solid var(--ant-color-border)',
          }}
        >
          2. 设备分配详情（单位：用户定义单位）
        </h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {devices.map((device, index) => {
            const loadRate = calculateLoadRate(device)
            return (
              <Card
                key={index}
                size="small"
                style={{ background: 'var(--ant-color-fill-tertiary)' }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    marginBottom: 12,
                    flexWrap: 'wrap',
                    gap: 8,
                  }}
                >
                  <h4 style={{ margin: 0 }}>
                    {device.name}（最小负荷: {device.minOperatingLoad}）
                  </h4>
                  <div
                    style={{
                      display: 'flex',
                      gap: 16,
                      fontSize: 14,
                      color: 'var(--ant-color-text-secondary)',
                    }}
                  >
                    <span>分配量: {device.maxCapacity}</span>
                    <span>总处理量: {device.total}</span>
                    <span>负荷率: {loadRate}%</span>
                  </div>
                </div>
                <Progress
                  percent={loadRate}
                  strokeColor={getProgressColor(loadRate)}
                  style={{ marginBottom: 12 }}
                />
                <Table
                  dataSource={device.objects || []}
                  pagination={false}
                  size="small"
                  bordered
                  columns={[
                    { title: '优化对象', dataIndex: 'name', width: 180 },
                    { title: '分配量', dataIndex: 'amount', render: (v: number) => `${v}` },
                  ]}
                />
              </Card>
            )
          })}
        </div>
      </Card>

      <Card style={{ marginBottom: 24 }}>
        <h3
          style={{
            fontSize: 16,
            fontWeight: 600,
            marginBottom: 20,
            paddingBottom: 10,
            borderBottom: '1px solid var(--ant-color-border)',
          }}
        >
          3. 优化对象用量汇总（单位：用户定义单位）
        </h3>
        <Table
          dataSource={manipulatedObjects}
          pagination={false}
          size="small"
          bordered
          columns={[
            { title: '优化对象', dataIndex: 'name', width: 180 },
            { title: '总可用量', dataIndex: 'totalAvailable', render: (v: number) => `${v}` },
            { title: '总分配量', dataIndex: 'totalAllocated', render: (v: number) => `${v}` },
            {
              title: '使用率',
              dataIndex: 'usageRate',
              render: (_v: unknown, record: ResultManipulatedObject) => {
                const pct = calculatePercentage(record.totalAllocated, record.totalAvailable)
                return (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <span>{pct}%</span>
                    <Progress
                      percent={pct}
                      strokeColor={getProgressColor(pct)}
                      strokeWidth={8}
                      showInfo={false}
                      style={{ flex: 1 }}
                    />
                  </div>
                )
              },
            },
          ]}
        />
      </Card>

      <div style={{ textAlign: 'center', marginTop: 24 }}>
        <Button type="primary" size="large" onClick={onReset}>
          重新优化参数
        </Button>
      </div>
    </div>
  )
}
