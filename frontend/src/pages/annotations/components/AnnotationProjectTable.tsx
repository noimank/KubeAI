import { Button, Popconfirm, Progress, Space, Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import type { AnnotationProject } from '@/types/annotation'

const ANNOTATION_TYPE_MAP: Record<string, { label: string; color: string }> = {
  image_classification: { label: '图像分类', color: 'blue' },
  object_detection: { label: '目标检测', color: 'green' },
  image_segmentation: { label: '图像分割', color: 'purple' },
  text_classification: { label: '文本分类', color: 'orange' },
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  active: { label: '活跃', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  archived: { label: '已归档', color: 'warning' },
}

interface AnnotationProjectTableProps {
  data: AnnotationProject[] | undefined
  loading: boolean
  total: number
  page: number
  pageSize: number
  onPageChange: (page: number, pageSize: number) => void
  onDelete: (id: string) => void
  canManage: boolean
}

export default function AnnotationProjectTable({
  data,
  loading,
  total,
  page,
  pageSize,
  onPageChange,
  onDelete,
  canManage,
}: AnnotationProjectTableProps) {
  const columns: ColumnsType<AnnotationProject> = [
    {
      title: '项目名称',
      dataIndex: 'name',
      ellipsis: true,
      render: (name: string, record: AnnotationProject) => (
        <Link to={`/annotations/${record.id}`}>{name}</Link>
      ),
    },
    {
      title: '数据集',
      width: 200,
      render: (_, record) => {
        if (!record.datasetName) return '-'
        const version = record.datasetVersionNumber ? ` v${record.datasetVersionNumber}` : ''
        return `${record.datasetName}${version}`
      },
    },
    {
      title: '标注类型',
      dataIndex: 'annotationType',
      width: 120,
      render: (type: string) => {
        const info = ANNOTATION_TYPE_MAP[type] || { label: type, color: 'default' }
        return <Tag color={info.color}>{info.label}</Tag>
      },
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
          {canManage && (
            <Popconfirm
              title="确认删除该标注项目？"
              description="删除后，LabelStudio 中的项目和标注数据将被同步删除，此操作不可恢复。"
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
