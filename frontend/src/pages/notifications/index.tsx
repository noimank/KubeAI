import { useState } from 'react'
import { Table, Tag, Segmented, Typography } from 'antd'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import type { ColumnsType } from 'antd/es/table'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'
import { getNotifications, markAsRead } from '@/services/notifications'
import type { Notification, NotificationType } from '@/types/notification'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const TYPE_CONFIG: Record<NotificationType, { color: string; text: string }> = {
  training_job: { color: 'blue', text: '训练任务' },
  quota_alert: { color: 'red', text: '配额告警' },
  annotation_task: { color: 'purple', text: '标注任务' },
  inference_service: { color: 'orange', text: '推理服务' },
}

const PRIORITY_CONFIG: Record<string, { color: string; text: string }> = {
  high: { color: 'red', text: '高' },
  medium: { color: 'orange', text: '中' },
  low: { color: 'blue', text: '低' },
}

const FILTER_OPTIONS = [
  { label: '全部', value: '' },
  { label: '训练', value: 'training_job' },
  { label: '配额', value: 'quota_alert' },
  { label: '标注', value: 'annotation_task' },
  { label: '推理', value: 'inference_service' },
]

export default function NotificationsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [filter, setFilter] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  const { data, isLoading } = useQuery({
    queryKey: ['notifications', filter, page, pageSize],
    queryFn: () =>
      getNotifications({
        current: page,
        pageSize,
        type: (filter || undefined) as NotificationType | undefined,
      }),
  })

  const readMutation = useMutation({
    mutationFn: markAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
    },
  })

  const handleRowClick = (record: Notification) => {
    if (!record.isRead) {
      readMutation.mutate(record.id)
    }
    if (record.resourceType && record.resourceId) {
      const routeMap: Record<string, string> = {
        training_job: `/training-jobs/${record.resourceId}`,
        inference_service: `/inference/${record.resourceId}`,
        annotation_project: `/annotations/${record.resourceId}`,
        dataset: `/datasets/${record.resourceId}`,
      }
      const route = routeMap[record.resourceType]
      if (route) {
        navigate(route)
      }
    }
  }

  const columns: ColumnsType<Notification> = [
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 100,
      render: (type: NotificationType) => {
        const cfg = TYPE_CONFIG[type] || { color: 'default', text: type }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '标题',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      render: (title: string, record) => (
        <span style={{ fontWeight: record.isRead ? 400 : 600 }}>{title}</span>
      ),
    },
    {
      title: '内容',
      dataIndex: 'content',
      key: 'content',
      ellipsis: true,
      render: (content: string) => <span style={{ color: 'rgba(0,0,0,0.45)' }}>{content}</span>,
    },
    {
      title: '优先级',
      dataIndex: 'priority',
      key: 'priority',
      width: 80,
      render: (priority: string) => {
        const cfg = PRIORITY_CONFIG[priority] || { color: 'default', text: priority }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 140,
      render: (v: string) => dayjs(v).format('MM-DD HH:mm'),
    },
    {
      title: '状态',
      dataIndex: 'isRead',
      key: 'isRead',
      width: 80,
      render: (isRead: boolean) =>
        isRead ? (
          <span style={{ color: 'rgba(0,0,0,0.45)' }}>已读</span>
        ) : (
          <Tag color="blue">未读</Tag>
        ),
    },
  ]

  const items = data?.data?.items ?? []
  const total = data?.data?.total ?? 0

  return (
    <div>
      <Typography.Title level={3} style={{ marginBottom: 24 }}>
        通知中心
      </Typography.Title>

      <div style={{ marginBottom: 16 }}>
        <Segmented
          options={FILTER_OPTIONS}
          value={filter}
          onChange={(v) => {
            setFilter(v as string)
            setPage(1)
          }}
        />
      </div>

      <Table<Notification>
        columns={columns}
        dataSource={items}
        loading={isLoading}
        rowKey="id"
        size="middle"
        onRow={(record) => ({
          onClick: () => handleRowClick(record),
          style: { cursor: 'pointer' },
        })}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: (p, ps) => {
            setPage(p)
            setPageSize(ps)
          },
        }}
      />
    </div>
  )
}
