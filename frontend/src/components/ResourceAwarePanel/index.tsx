import { Card, Progress, Space, Spin, Typography } from 'antd'
import { CheckCircleOutlined, ExclamationCircleOutlined, WarningOutlined } from '@ant-design/icons'
import { useResourceQuota } from '@/hooks/useResourceQuota'

const LEVEL_COLOR: Record<string, string> = {
  ok: '#52c41a',
  warning: '#faad14',
  danger: '#ff4d4f',
}

const LEVEL_TIP: Record<string, { icon: React.ReactNode; text: string }> = {
  ok: {
    icon: <CheckCircleOutlined style={{ color: '#52c41a' }} />,
    text: '资源充足，可以提交',
  },
  warning: {
    icon: <ExclamationCircleOutlined style={{ color: '#faad14' }} />,
    text: '资源偏紧，请注意配额',
  },
  danger: {
    icon: <WarningOutlined style={{ color: '#ff4d4f' }} />,
    text: '资源不足，请释放资源或联系管理员',
  },
}

export default function ResourceAwarePanel() {
  const { quota, isLoading, formatMemoryMi } = useResourceQuota()

  if (isLoading) {
    return (
      <Card title="资源配额" size="small">
        <div style={{ textAlign: 'center', padding: '20px 0' }}>
          <Spin />
        </div>
      </Card>
    )
  }

  if (!quota) {
    return (
      <Card title="资源配额" size="small">
        <Typography.Text type="secondary">暂无配额信息</Typography.Text>
      </Card>
    )
  }

  const overallLevel =
    quota.gpu.level === 'danger' || quota.cpu.level === 'danger' || quota.memory.level === 'danger'
      ? 'danger'
      : quota.gpu.level === 'warning' ||
          quota.cpu.level === 'warning' ||
          quota.memory.level === 'warning'
        ? 'warning'
        : 'ok'

  const tip = LEVEL_TIP[overallLevel]

  return (
    <Card title="资源配额" size="small">
      <Space direction="vertical" style={{ width: '100%' }} size={16}>
        <ResourceRow
          label="GPU"
          used={`${quota.gpu.used}`}
          total={`${quota.gpu.total}`}
          percent={quota.gpu.percent}
          level={quota.gpu.level}
          unit="张"
        />
        <ResourceRow
          label="CPU"
          used={`${quota.cpu.used}`}
          total={`${quota.cpu.total}`}
          percent={quota.cpu.percent}
          level={quota.cpu.level}
          unit="核"
        />
        <ResourceRow
          label="内存"
          used={formatMemoryMi(quota.memory.used)}
          total={formatMemoryMi(quota.memory.total)}
          percent={quota.memory.percent}
          level={quota.memory.level}
        />
        <ResourceRow
          label="存储"
          used={formatMemoryMi(quota.storage.used)}
          total={formatMemoryMi(quota.storage.total)}
          percent={quota.storage.percent}
          level={quota.storage.level}
        />
      </Space>
      <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 6 }}>
        {tip.icon}
        <Typography.Text style={{ fontSize: 12 }}>{tip.text}</Typography.Text>
      </div>
    </Card>
  )
}

function ResourceRow({
  label,
  used,
  total,
  percent,
  level,
  unit,
}: {
  label: string
  used: string
  total: string
  percent: number
  level: string
  unit?: string
}) {
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
        <Typography.Text strong style={{ fontSize: 13 }}>
          {label}
        </Typography.Text>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          {used} / {total} {unit ?? ''}
        </Typography.Text>
      </div>
      <Progress
        percent={Math.min(percent, 100)}
        showInfo={false}
        strokeColor={LEVEL_COLOR[level]}
        size="small"
      />
    </div>
  )
}
