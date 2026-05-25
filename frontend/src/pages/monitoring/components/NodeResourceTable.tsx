import { Progress, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { NodeResourceDetail as NodeDetail } from '@/types/monitoring'

interface Props {
  data: NodeDetail[]
  loading: boolean
}

function getUtilColor(pct: number): string {
  if (pct > 85) return '#ff4d4f'
  if (pct > 60) return '#faad14'
  return '#52c41a'
}

function getCondStatus(conditions: NodeDetail['conditions']): string {
  const ready = conditions.find((c) => c.type === 'Ready')
  return ready?.status === 'True' ? 'Ready' : 'NotReady'
}

const columns: ColumnsType<NodeDetail> = [
  {
    title: '节点名称',
    dataIndex: 'name',
    key: 'name',
    ellipsis: true,
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (_, record) => {
      const s = getCondStatus(record.conditions)
      return s === 'Ready' ? <Tag color="green">Ready</Tag> : <Tag color="red">{s}</Tag>
    },
  },
  {
    title: 'GPU',
    key: 'gpu',
    width: 160,
    render: (_, record) => {
      const { allocatable, allocated } = record.gpu
      const pct = allocatable > 0 ? Math.round((allocated / allocatable) * 100) : 0
      return (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Progress type="circle" size={40} percent={pct} strokeColor={getUtilColor(pct)} />
          <span>
            {allocated}/{allocatable}
          </span>
        </div>
      )
    },
  },
  {
    title: 'CPU',
    key: 'cpu',
    width: 160,
    render: (_, record) => {
      const { allocatable, allocated } = record.cpu
      const pct = allocatable > 0 ? Math.round((allocated / allocatable) * 100) : 0
      return <Progress percent={pct} strokeColor={getUtilColor(pct)} size="small" />
    },
  },
  {
    title: '内存',
    key: 'memory',
    width: 160,
    render: (_, record) => {
      const { allocatable, allocated } = record.memory
      const pct = allocatable > 0 ? Math.round((allocated / allocatable) * 100) : 0
      return <Progress percent={pct} strokeColor={getUtilColor(pct)} size="small" />
    },
  },
]

export default function NodeResourceTable({ data, loading }: Props) {
  return (
    <Table<NodeDetail>
      rowKey="name"
      columns={columns}
      dataSource={data}
      loading={loading}
      pagination={false}
      size="small"
    />
  )
}
