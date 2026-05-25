import { Progress, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { TenantResourceSummary as TenantSummary } from '@/types/monitoring'

interface Props {
  data: TenantSummary[]
  loading: boolean
  onRowClick: (tenantId: string) => void
}

function getUtilColor(pct: number): string {
  if (pct > 85) return '#ff4d4f'
  if (pct > 60) return '#faad14'
  return '#52c41a'
}

function toNum(v: number | string): number {
  return typeof v === 'number' ? v : parseFloat(v) || 0
}

function renderQuotaProgress(used: number | string, quota: number | string) {
  const u = toNum(used)
  const q = toNum(quota)
  const pct = q > 0 ? Math.round((u / q) * 100) : 0
  return (
    <div style={{ minWidth: 80 }}>
      <Progress percent={pct} strokeColor={getUtilColor(pct)} size="small" />
    </div>
  )
}

const columns: ColumnsType<TenantSummary> = [
  {
    title: '租户',
    dataIndex: 'tenantName',
    key: 'tenantName',
    ellipsis: true,
    width: 'auto',
  },
  {
    title: 'GPU',
    key: 'gpu',
    width: 120,
    render: (_, record) => renderQuotaProgress(record.gpu.used, record.gpu.quota),
  },
  {
    title: 'CPU',
    key: 'cpu',
    width: 120,
    render: (_, record) => renderQuotaProgress(record.cpu.used, record.cpu.quota),
  },
  {
    title: '内存',
    key: 'memory',
    width: 120,
    render: (_, record) => renderQuotaProgress(record.memory.used, record.memory.quota),
  },
  {
    title: '任务',
    dataIndex: 'activeJobsCount',
    key: 'activeJobsCount',
    width: 56,
    align: 'center',
  },
  {
    title: '服务',
    dataIndex: 'runningServicesCount',
    key: 'runningServicesCount',
    width: 56,
    align: 'center',
  },
]

export default function TenantResourceTable({ data, loading, onRowClick }: Props) {
  return (
    <Table<TenantSummary>
      rowKey="tenantId"
      columns={columns}
      dataSource={data}
      loading={loading}
      pagination={false}
      size="small"
      scroll={{ x: 500 }}
      onRow={(record) => ({
        onClick: () => onRowClick(record.tenantId),
        style: { cursor: 'pointer' },
      })}
    />
  )
}
