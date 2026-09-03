import { Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import type { RecentInferenceService } from '@/types/dashboard'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '部署中' },
  deploying: { color: 'processing', text: '部署中' },
  running: { color: 'success', text: '运行中' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

interface Props {
  data: RecentInferenceService[]
}

export default function RecentInferenceServices({ data }: Props) {
  const columns: ColumnsType<RecentInferenceService> = [
    {
      title: '服务名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string, record) => <Link to={`/inference/${record.id}`}>{name}</Link>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (status: string) => {
        const cfg = STATUS_CONFIG[status] || { color: 'default', text: status }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '副本数',
      dataIndex: 'replicas',
      key: 'replicas',
      width: 80,
    },
    {
      title: '端点',
      dataIndex: 'endpointUrl',
      key: 'endpointUrl',
      width: 160,
      ellipsis: true,
      render: (url?: string) => url || '—',
    },
  ]

  return (
    <Table<RecentInferenceService>
      columns={columns}
      dataSource={data}
      rowKey="id"
      size="small"
      pagination={false}
    />
  )
}
