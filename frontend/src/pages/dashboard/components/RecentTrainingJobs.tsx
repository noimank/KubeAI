import { Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import type { RecentTrainingJob } from '@/types/dashboard'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '等待中' },
  queued: { color: 'warning', text: '排队中' },
  initializing: { color: 'processing', text: '初始化' },
  running: { color: 'processing', text: '运行中' },
  succeeded: { color: 'success', text: '已完成' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

interface Props {
  data: RecentTrainingJob[]
  loading: boolean
}

export default function RecentTrainingJobs({ data, loading }: Props) {
  const columns: ColumnsType<RecentTrainingJob> = [
    {
      title: '任务名称',
      dataIndex: 'name',
      key: 'name',
      ellipsis: true,
      render: (name: string, record) => <Link to={`/training-jobs/${record.id}`}>{name}</Link>,
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
      title: 'GPU',
      dataIndex: 'gpuCount',
      key: 'gpuCount',
      width: 70,
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 120,
      render: (v: string) => dayjs(v).fromNow(),
    },
  ]

  return (
    <Table<RecentTrainingJob>
      columns={columns}
      dataSource={data}
      loading={loading}
      rowKey="id"
      size="small"
      pagination={false}
      footer={() => <Link to="/training-jobs">查看全部</Link>}
    />
  )
}
