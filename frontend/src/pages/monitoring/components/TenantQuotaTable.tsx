import { useMemo } from 'react'
import { Button, Progress, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { TenantQuotaComparison as QuotaRow } from '@/types/monitoring'
import { formatKi } from '@/utils/format'

interface Props {
  data: QuotaRow[]
  loading: boolean
  onTransfer: (tenant?: QuotaRow) => void
}

function getUtilColor(pct: number): string {
  if (pct > 85) return '#ff4d4f'
  if (pct > 60) return '#faad14'
  return '#52c41a'
}

function renderUtilColumn(used: number, quota: number, isMemory: boolean) {
  const pct = quota > 0 ? Math.round((used / quota) * 100) : 0
  const usedStr = isMemory ? formatKi(used) : `${used}`
  const quotaStr = isMemory ? formatKi(quota) : `${quota}`
  return (
    <div style={{ minWidth: 100 }}>
      <div style={{ fontSize: 12, marginBottom: 2 }}>
        {usedStr} / {quotaStr}
      </div>
      <Progress percent={pct} strokeColor={getUtilColor(pct)} size="small" />
    </div>
  )
}

export default function TenantQuotaTable({ data, loading, onTransfer }: Props) {
  const columns: ColumnsType<QuotaRow> = useMemo(
    () => [
      {
        title: '租户',
        dataIndex: 'tenantName',
        key: 'tenantName',
        ellipsis: true,
        width: 120,
      },
      {
        title: 'GPU',
        key: 'gpu',
        width: 130,
        sorter: (a, b) => a.gpu.utilization - b.gpu.utilization,
        render: (_, r) => renderUtilColumn(r.gpu.used, r.gpu.quota, false),
      },
      {
        title: 'CPU',
        key: 'cpu',
        width: 130,
        sorter: (a, b) => a.cpu.utilization - b.cpu.utilization,
        render: (_, r) => renderUtilColumn(r.cpu.used, r.cpu.quota, false),
      },
      {
        title: '内存',
        key: 'memory',
        width: 130,
        sorter: (a, b) => a.memory.utilization - b.memory.utilization,
        render: (_, r) => renderUtilColumn(r.memory.used, r.memory.quota, true),
      },
      {
        title: '存储',
        key: 'storage',
        width: 130,
        sorter: (a, b) => a.storage.utilization - b.storage.utilization,
        render: (_, r) => renderUtilColumn(r.storage.used, r.storage.quota, true),
      },
      {
        title: '操作',
        key: 'action',
        width: 80,
        fixed: 'right',
        render: (_, record) => (
          <Button
            type="link"
            size="small"
            onClick={(e) => {
              e.stopPropagation()
              onTransfer(record)
            }}
          >
            调配
          </Button>
        ),
      },
    ],
    [onTransfer],
  )

  return (
    <Table<QuotaRow>
      rowKey="tenantId"
      columns={columns}
      dataSource={data}
      loading={loading}
      pagination={false}
      size="small"
      scroll={{ x: 700 }}
    />
  )
}
