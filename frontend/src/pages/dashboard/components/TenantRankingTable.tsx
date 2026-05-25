import { Progress, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { TenantRankingItem } from '@/types/dashboard'

interface Props {
  data: TenantRankingItem[]
  loading: boolean
}

function getUtilColor(pct: number): string {
  if (pct > 85) return 'red'
  if (pct > 60) return 'orange'
  return 'green'
}

export default function TenantRankingTable({ data, loading }: Props) {
  const columns: ColumnsType<TenantRankingItem> = [
    {
      title: '租户',
      dataIndex: 'tenantName',
      key: 'tenantName',
      ellipsis: true,
    },
    {
      title: 'GPU 配额/已用',
      key: 'gpu',
      width: 180,
      render: (_, record) => (
        <span>
          {record.gpuUsed} / {record.gpuQuota}
          <Progress
            percent={record.gpuUtilization}
            size="small"
            strokeColor={getUtilColor(record.gpuUtilization)}
            style={{ width: 80, marginLeft: 8, display: 'inline-block' }}
          />
        </span>
      ),
    },
    {
      title: 'CPU 利用率',
      dataIndex: 'cpuUtilization',
      key: 'cpuUtilization',
      width: 100,
      render: (v: number) => <Tag color={getUtilColor(v)}>{v}%</Tag>,
    },
    {
      title: '任务数',
      dataIndex: 'activeJobs',
      key: 'activeJobs',
      width: 80,
    },
  ]

  return (
    <Table<TenantRankingItem>
      columns={columns}
      dataSource={data}
      loading={loading}
      rowKey="tenantId"
      size="small"
      pagination={false}
    />
  )
}
