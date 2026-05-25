import { Progress, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { TenantResourceSummary as TenantSummary } from '@/types/monitoring'
import { formatKi, parseK8sQuantity } from '@/utils/format'

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

function renderQuotaProgress(
  used: number | string,
  quota: number | string,
  type: 'gpu' | 'cpu' | 'memory' | 'storage',
) {
  const u = parseK8sQuantity(used)
  const q = parseK8sQuantity(quota)
  const pct = q > 0 ? Math.round((u / q) * 100) : 0

  let usedStr: string
  let quotaStr: string
  if (type === 'memory' || type === 'storage') {
    usedStr = formatKi(u)
    quotaStr = formatKi(q)
  } else if (type === 'cpu') {
    usedStr = `${u} 核`
    quotaStr = `${q} 核`
  } else {
    usedStr = `${u}`
    quotaStr = `${q}`
  }

  return (
    <div style={{ minWidth: 100 }}>
      <div style={{ fontSize: 12, marginBottom: 2 }}>
        {usedStr} / {quotaStr}
      </div>
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
    render: (_, record) => renderQuotaProgress(record.gpu.used, record.gpu.quota, 'gpu'),
  },
  {
    title: 'CPU',
    key: 'cpu',
    width: 120,
    render: (_, record) => renderQuotaProgress(record.cpu.used, record.cpu.quota, 'cpu'),
  },
  {
    title: '内存',
    key: 'memory',
    width: 120,
    render: (_, record) => renderQuotaProgress(record.memory.used, record.memory.quota, 'memory'),
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
