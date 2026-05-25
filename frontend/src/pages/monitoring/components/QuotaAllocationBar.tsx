import { Progress, Space, Typography } from 'antd'
import type { QuotaAllocationOverview } from '@/types/monitoring'

interface Props {
  data: QuotaAllocationOverview | null
}

const RESOURCE_LABELS = [
  { key: 'gpu' as const, label: 'GPU', unit: '张', format: (v: number) => `${v}` },
  { key: 'cpu' as const, label: 'CPU', unit: '核', format: (v: number) => `${v}` },
  { key: 'memory' as const, label: '内存', unit: '', format: formatMemory },
  { key: 'storage' as const, label: '存储', unit: '', format: formatMemory },
]

function formatMemory(ki: number): string {
  if (ki >= 1024 ** 2) return `${(ki / 1024 ** 2).toFixed(0)} Gi`
  if (ki >= 1024) return `${(ki / 1024).toFixed(0)} Mi`
  return `${ki} Ki`
}

export default function QuotaAllocationBar({ data }: Props) {
  if (!data) return null

  return (
    <Space direction="vertical" style={{ width: '100%' }} size={12}>
      {RESOURCE_LABELS.map(({ key, label, unit, format }) => {
        const item = data[key]
        const pct = item.total > 0 ? Math.round((item.allocated / item.total) * 100) : 0
        return (
          <div key={key}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: 4,
              }}
            >
              <Typography.Text strong style={{ fontSize: 13 }}>
                {label}
              </Typography.Text>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                已分配 {format(item.allocated)} / 总量 {format(item.total)} {unit}
                {item.available > 0 && ` (可分配 ${format(item.available)})`}
              </Typography.Text>
            </div>
            <Progress
              percent={pct}
              strokeColor={pct > 85 ? '#ff4d4f' : pct > 60 ? '#faad14' : '#1890ff'}
              size="small"
            />
          </div>
        )
      })}
    </Space>
  )
}
