import { Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { StaleJob } from '@/types/monitoring'

const statusColorMap: Record<string, string> = {
  succeeded: 'green',
  failed: 'red',
  stopped: 'orange',
}

interface Props {
  data: StaleJob[]
  loading: boolean
}

const columns: ColumnsType<StaleJob> = [
  { title: '任务名称', dataIndex: 'name', key: 'name', ellipsis: true },
  { title: '租户', dataIndex: 'tenantName', key: 'tenantName', ellipsis: true },
  {
    title: '状态',
    dataIndex: 'status',
    key: 'status',
    width: 100,
    render: (status: string) => <Tag color={statusColorMap[status] || 'default'}>{status}</Tag>,
  },
  {
    title: '完成时间',
    dataIndex: 'finishedAt',
    key: 'finishedAt',
    width: 180,
    render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-'),
  },
  {
    title: '距今天数',
    dataIndex: 'daysAgo',
    key: 'daysAgo',
    width: 100,
    render: (v: number) => `${v} 天`,
  },
  {
    title: 'VCJob 名称',
    dataIndex: 'vcjobName',
    key: 'vcjobName',
    ellipsis: true,
  },
]

export default function StaleJobTable({ data, loading }: Props) {
  return (
    <Table<StaleJob>
      columns={columns}
      dataSource={data}
      loading={loading}
      rowKey="id"
      size="small"
      pagination={false}
      locale={{ emptyText: '暂无过期任务资源' }}
    />
  )
}
