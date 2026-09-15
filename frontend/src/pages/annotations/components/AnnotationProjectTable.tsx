import { Button, Empty, Popconfirm, Progress, Space, Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import type { AnnotationProject } from '@/types/annotation'
import { formatDate } from '@/utils/format'
import { STATUS_MAP } from '../utils/projectStatus'

interface AnnotationProjectTableProps {
  data: AnnotationProject[] | undefined
  loading: boolean
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number, pageSize: number) => void
  onDelete: (id: string) => void
  onRetry?: (id: string) => void
  retryingId?: string | null
  canManage: boolean
  onCreateClick?: () => void
}

export default function AnnotationProjectTable({
  data,
  loading,
  total,
  page,
  pageSize,
  onPageChange,
  onDelete,
  onRetry,
  retryingId,
  canManage,
  onCreateClick,
}: AnnotationProjectTableProps) {
  const columns: ColumnsType<AnnotationProject> = [
    {
      title: '项目名称',
      dataIndex: 'name',
      width: 220,
      ellipsis: true,
      fixed: 'left',
      render: (name: string, record: AnnotationProject) => (
        <Link to={`/annotations/${record.id}`}>{name}</Link>
      ),
    },
    {
      title: '数据集',
      dataIndex: 'datasetName',
      width: 180,
      ellipsis: true,
      render: (datasetName: string | undefined) => datasetName || '-',
    },
    {
      title: '版本',
      dataIndex: 'datasetVersionNumber',
      width: 90,
      render: (version: number | undefined) => (version ? `v${version}` : '-'),
    },
    {
      title: '标注模板',
      dataIndex: 'templateName',
      width: 120,
      ellipsis: true,
      render: (name: string | null | undefined) => (
        <Tag
          color="blue"
          style={{
            maxWidth: '100%',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {name || '—'}
        </Tag>
      ),
    },
    {
      title: '进度',
      width: 180,
      render: (_, record) => (
        <Progress
          percent={record.progressPercent}
          size="small"
          format={() => `${record.completedTasks}/${record.totalTasks}`}
        />
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: string) => {
        const info = STATUS_MAP[status] || { label: status, color: 'default' }
        return <Tag color={info.color}>{info.label}</Tag>
      },
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
      render: (v: string) => formatDate(v),
    },
    {
      title: '操作',
      width: 120,
      render: (_, record) => (
        <Space size="small">
          <Link to={`/annotations/${record.id}`}>
            <Button type="link" size="small">
              详情
            </Button>
          </Link>
          {canManage && record.status === 'failed' && onRetry && (
            <Button
              type="link"
              size="small"
              loading={retryingId === record.id}
              onClick={() => onRetry(record.id)}
            >
              重试
            </Button>
          )}
          {canManage && (
            <Popconfirm
              title="确认删除该标注项目？"
              description="删除后，项目和标注数据将被同步删除，此操作不可恢复。"
              onConfirm={() => onDelete(record.id)}
              okText="确认"
              cancelText="取消"
            >
              <Button type="link" size="small" danger>
                删除
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Table<AnnotationProject>
      rowKey="id"
      columns={columns}
      dataSource={data}
      loading={loading}
      scroll={{ x: 1200 }}
      locale={{
        emptyText: (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <Space direction="vertical" align="center">
                <span>还没有标注项目</span>
                {canManage && onCreateClick && (
                  <Button type="primary" onClick={onCreateClick}>
                    选择数据集创建标注任务
                  </Button>
                )}
              </Space>
            }
          />
        ),
      }}
      pagination={{
        current: page,
        pageSize,
        total,
        showSizeChanger: true,
        pageSizeOptions: ['20', '50', '100'],
        showTotal: (t) => `共 ${t} 条`,
        onChange: onPageChange,
      }}
    />
  )
}
