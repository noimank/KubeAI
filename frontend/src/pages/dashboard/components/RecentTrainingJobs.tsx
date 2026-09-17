import { Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import type { RecentTrainingJob } from '@/types/dashboard'
import { TRAINING_JOB_STATUS_CONFIG } from '@/utils/constants'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

interface Props {
  data: RecentTrainingJob[]
}

export default function RecentTrainingJobs({ data }: Props) {
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
        const cfg = TRAINING_JOB_STATUS_CONFIG[status] || { color: 'default', text: status }
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
      rowKey="id"
      size="small"
      pagination={false}
      footer={() => <Link to="/training-jobs">查看全部</Link>}
    />
  )
}
