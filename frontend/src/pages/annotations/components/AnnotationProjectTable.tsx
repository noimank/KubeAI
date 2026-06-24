import { Button, Empty, Popconfirm, Progress, Space, Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import type { ColumnsType } from 'antd/es/table'
import type { AnnotationProject, AnnotationCallbackStatus } from '@/types/annotation'
import { formatDate } from '@/utils/format'

const ANNOTATION_TYPE_MAP: Record<string, { label: string; color: string }> = {
  image_classification: { label: '图像分类', color: 'blue' },
  object_detection: { label: '目标检测', color: 'green' },
  image_segmentation: { label: '图像分割', color: 'purple' },
  text_classification: { label: '文本分类', color: 'orange' },
  choices: { label: '分类选择', color: 'blue' },
  rectanglelabels: { label: '矩形框', color: 'green' },
  polygonlabels: { label: '多边形', color: 'purple' },
  textarea: { label: '文本填写', color: 'orange' },
  rating: { label: '评分', color: 'gold' },
}

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  draft: { label: '草稿', color: 'default' },
  active: { label: '活跃', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  archived: { label: '已归档', color: 'warning' },
}

const CALLBACK_STATUS_MAP: Record<AnnotationCallbackStatus, { label: string; color: string }> = {
  pending: { label: '等待', color: 'processing' },
  running: { label: '回流中', color: 'processing' },
  succeeded: { label: '已回流', color: 'success' },
  failed: { label: '失败', color: 'error' },
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
  canManage,
  onCreateClick,
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
      title: '回流',
      dataIndex: 'callbackStatus',
      width: 100,
      render: (callbackStatus: AnnotationCallbackStatus | undefined) => {
        if (!callbackStatus || callbackStatus === 'pending') return '-'
        const info = CALLBACK_STATUS_MAP[callbackStatus] || {
          label: callbackStatus,
          color: 'default',
        }
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
