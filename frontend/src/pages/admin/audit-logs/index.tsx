import { useRef } from 'react'
import { Button, Tag, Typography } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { ProTable } from '@ant-design/pro-components'
import type { ActionType, ProColumns } from '@ant-design/pro-components'
import { getAuditLogs } from '@/services/audit'
import type { AuditLog, AuditAction, ResourceType } from '@/types/audit'

const ACTION_LABELS: Record<AuditAction, string> = {
  create: '创建',
  update: '更新',
  delete: '删除',
  login: '登录',
  logout: '登出',
  register: '注册',
  enable: '启用',
  disable: '禁用',
  invite: '邀请',
  accept_invite: '接受邀请',
  cancel_invite: '取消邀请',
  update_role: '变更角色',
  remove_member: '移除成员',
  update_quota: '调整配额',
}

const ACTION_COLORS: Record<string, string> = {
  create: 'green',
  update: 'blue',
  delete: 'red',
  login: 'cyan',
  logout: 'default',
  register: 'purple',
  enable: 'green',
  disable: 'red',
  invite: 'blue',
  accept_invite: 'green',
  cancel_invite: 'orange',
  update_role: 'blue',
  remove_member: 'red',
  update_quota: 'geekblue',
}

const RESOURCE_LABELS: Record<ResourceType, string> = {
  tenant: '租户',
  user: '用户',
  quota: '配额',
  membership: '成员关系',
  invitation: '邀请',
  credential: '凭证',
}

const RESOURCE_COLORS: Record<string, string> = {
  tenant: 'blue',
  user: 'purple',
  quota: 'orange',
  membership: 'cyan',
  invitation: 'green',
  credential: 'default',
}

const ACTION_OPTIONS = Object.entries(ACTION_LABELS).map(([value, label]) => ({
  label,
  value,
}))

const RESOURCE_OPTIONS = Object.entries(RESOURCE_LABELS).map(([value, label]) => ({
  label,
  value,
}))

function DetailPanel({ record }: { record: AuditLog }) {
  return (
    <div style={{ padding: '12px 0' }}>
      {record.detail && Object.keys(record.detail).length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <Typography.Text type="secondary">操作详情：</Typography.Text>
          <Typography.Paragraph copyable style={{ marginBottom: 4, whiteSpace: 'pre-wrap' }}>
            {JSON.stringify(record.detail, null, 2)}
          </Typography.Paragraph>
        </div>
      )}
      {record.userAgent && (
        <div style={{ marginBottom: 4 }}>
          <Typography.Text type="secondary">User-Agent：</Typography.Text>
          <Typography.Text style={{ fontSize: 12 }}>{record.userAgent}</Typography.Text>
        </div>
      )}
      {record.requestId && (
        <div>
          <Typography.Text type="secondary">Request ID：</Typography.Text>
          <Typography.Text code style={{ fontSize: 12 }}>
            {record.requestId}
          </Typography.Text>
        </div>
      )}
    </div>
  )
}

export default function AuditLogsPage() {
  const actionRef = useRef<ActionType>(null)

  const columns: ProColumns<AuditLog>[] = [
    {
      title: '操作时间',
      dataIndex: 'createdAt',
      valueType: 'dateTime',
      width: 180,
      hideInSearch: true,
    },
    {
      title: '时间范围',
      dataIndex: 'timeRange',
      valueType: 'dateTimeRange',
      hideInTable: true,
      search: {
        transform: (value: [string, string]) => ({
          startTime: value[0],
          endTime: value[1],
        }),
      },
    },
    {
      title: '操作人',
      dataIndex: 'username',
      width: 150,
      fieldProps: { placeholder: '搜索用户名' },
      render: (_, record) =>
        record.username || (record.userId ? record.userId.substring(0, 8) + '...' : '系统'),
    },
    {
      title: '操作类型',
      dataIndex: 'action',
      width: 120,
      valueType: 'select',
      fieldProps: { mode: 'multiple', options: ACTION_OPTIONS, placeholder: '选择操作类型' },
      render: (_, record) => (
        <Tag color={ACTION_COLORS[record.action] || 'default'}>
          {ACTION_LABELS[record.action] || record.action}
        </Tag>
      ),
    },
    {
      title: '资源类型',
      dataIndex: 'resourceType',
      width: 120,
      valueType: 'select',
      fieldProps: { mode: 'multiple', options: RESOURCE_OPTIONS, placeholder: '选择资源类型' },
      render: (_, record) => (
        <Tag color={RESOURCE_COLORS[record.resourceType] || 'default'}>
          {RESOURCE_LABELS[record.resourceType] || record.resourceType}
        </Tag>
      ),
    },
    {
      title: '资源 ID',
      dataIndex: 'resourceId',
      width: 160,
      hideInSearch: true,
      render: (_, record) =>
        record.resourceId ? (
          <Typography.Text copyable style={{ fontSize: 12 }}>
            {record.resourceId.length > 12
              ? record.resourceId.substring(0, 12) + '...'
              : record.resourceId}
          </Typography.Text>
        ) : (
          '-'
        ),
    },
    {
      title: 'IP 地址',
      dataIndex: 'ipAddress',
      width: 140,
      hideInSearch: true,
    },
  ]

  return (
    <ProTable<AuditLog>
      columns={columns}
      actionRef={actionRef}
      request={async (params) => {
        const { current, pageSize, action, resourceType, username, startTime, endTime } = params
        const res = await getAuditLogs({
          page: current,
          pageSize,
          action: action?.length ? action : undefined,
          resourceType: resourceType?.length ? resourceType : undefined,
          username: username || undefined,
          startTime,
          endTime,
        })
        return {
          data: res.data?.items || [],
          total: res.data?.total || 0,
          success: res.success,
        }
      }}
      rowKey="id"
      search={{
        filterType: 'light',
        span: 6,
      }}
      expandable={{
        expandedRowRender: (record) => <DetailPanel record={record} />,
      }}
      toolBarRender={() => [
        <Button key="reload" icon={<ReloadOutlined />} onClick={() => actionRef.current?.reload()}>
          刷新
        </Button>,
      ]}
      pagination={{
        defaultPageSize: 20,
        showSizeChanger: true,
      }}
      locale={{
        emptyText: (
          <div style={{ padding: '24px 0', textAlign: 'center' }}>
            <p style={{ color: 'var(--text-tertiary)', marginBottom: 16 }}>
              暂无审计日志，操作记录会自动出现在这里
            </p>
          </div>
        ),
      }}
    />
  )
}
