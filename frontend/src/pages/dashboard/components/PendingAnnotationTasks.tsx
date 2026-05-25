import { Progress, Table } from 'antd'
import { Link } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import type { PendingAnnotationTask } from '@/types/dashboard'

interface Props {
  data: PendingAnnotationTask[]
  loading: boolean
}

export default function PendingAnnotationTasks({ data, loading }: Props) {
  const columns: ColumnsType<PendingAnnotationTask> = [
    {
      title: '项目名称',
      dataIndex: 'projectName',
      key: 'projectName',
      ellipsis: true,
      render: (name: string, record) => (
        <Link to={`/annotations/projects/${record.projectId}/workspace`}>{name}</Link>
      ),
    },
    {
      title: '待标注',
      key: 'pending',
      width: 90,
      render: (_, record) => record.totalTasks - record.completedTasks,
    },
    {
      title: '已完成',
      dataIndex: 'completedTasks',
      key: 'completedTasks',
      width: 90,
    },
    {
      title: '进度',
      key: 'progress',
      width: 150,
      render: (_, record) => {
        const pct =
          record.totalTasks > 0 ? Math.round((record.completedTasks / record.totalTasks) * 100) : 0
        return <Progress percent={pct} size="small" />
      },
    },
  ]

  return (
    <Table<PendingAnnotationTask>
      columns={columns}
      dataSource={data}
      loading={loading}
      rowKey="id"
      size="small"
      pagination={false}
    />
  )
}
