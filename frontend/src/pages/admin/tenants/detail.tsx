import { useEffect, useRef, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Breadcrumb,
  Button,
  Col,
  Descriptions,
  Drawer,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  message,
} from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import { ProTable } from '@ant-design/pro-components'
import type { ActionType, ProColumns } from '@ant-design/pro-components'
import TenantEditForm from './components/TenantEditForm'
import QuotaEditor from './components/QuotaEditor'
import InviteMemberModal from './components/InviteMemberModal'
import {
  getTenant,
  updateTenant,
  toggleTenantStatus,
  getTenantQuotaUsage,
  listMembers,
  updateMemberRole,
  removeMember,
} from '@/services/tenants'
import { getAuditLogs } from '@/services/audit'
import type { Tenant, TenantUpdateRequest, QuotaUsage, TenantMember } from '@/types/tenant'
import type { AuditLog, AuditAction, ResourceType } from '@/types/audit'

const STATUS_COLORS: Record<string, string> = { active: 'green', disabled: 'red' }
const STATUS_LABELS: Record<string, string> = { active: '正常', disabled: '已禁用' }

const ROLE_LABELS: Record<string, string> = {
  mlops: 'MLOps',
  engineer: '算法工程师',
  annotator: '标注员',
}
const ROLE_COLORS: Record<string, string> = {
  mlops: 'blue',
  engineer: 'green',
  annotator: 'orange',
}
const ROLE_OPTIONS = [
  { label: '算法工程师', value: 'engineer' },
  { label: 'MLOps', value: 'mlops' },
  { label: '标注员', value: 'annotator' },
]

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
const ACTION_OPTIONS = Object.entries(ACTION_LABELS).map(([value, label]) => ({ label, value }))
const RESOURCE_OPTIONS = Object.entries(RESOURCE_LABELS).map(([value, label]) => ({ label, value }))

function parseK8sQuantity(val: string): number {
  if (!val) return 0
  if (val.endsWith('Gi')) return parseFloat(val) * 1024
  if (val.endsWith('Mi')) return parseFloat(val)
  if (val.endsWith('Ki')) return parseFloat(val) / 1024
  if (val.endsWith('G')) return parseFloat(val) * 1000
  if (val.endsWith('M')) return parseFloat(val)
  if (val.endsWith('K')) return parseFloat(val) / 1000
  return parseFloat(val) || 0
}

function formatQuotaValue(val: string | number): string {
  if (typeof val === 'number') return `${val}`
  return val
}

export default function TenantDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [tenant, setTenant] = useState<Tenant | null>(null)
  const [usage, setUsage] = useState<QuotaUsage | null>(null)
  const [loading, setLoading] = useState(true)
  const [editDrawerOpen, setEditDrawerOpen] = useState(false)
  const [quotaDrawerOpen, setQuotaDrawerOpen] = useState(false)
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [members, setMembers] = useState<TenantMember[]>([])
  const [membersLoading, setMembersLoading] = useState(false)
  const [editingMemberId, setEditingMemberId] = useState<string | null>(null)
  const auditActionRef = useRef<ActionType>(null)

  const fetchData = async () => {
    if (!id) return
    setLoading(true)
    try {
      const [tenantRes, usageRes] = await Promise.all([getTenant(id), getTenantQuotaUsage(id)])
      if (tenantRes.success) setTenant(tenantRes.data ?? null)
      if (usageRes.success) setUsage(usageRes.data ?? null)
    } catch {
      // interceptor handles error toast
    } finally {
      setLoading(false)
    }
  }

  const fetchMembers = async () => {
    if (!id) return
    setMembersLoading(true)
    try {
      const res = await listMembers(id)
      if (res.success) setMembers(res.data || [])
    } catch {
      // interceptor handles error toast
    } finally {
      setMembersLoading(false)
    }
  }

  useEffect(() => {
    fetchData()
    fetchMembers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  const handleEdit = async (values: TenantUpdateRequest) => {
    if (!tenant) return
    try {
      await updateTenant(tenant.id, values)
      message.success('租户更新成功')
      setEditDrawerOpen(false)
      fetchData()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleToggleStatus = async () => {
    if (!tenant) return
    const targetStatus = tenant.status === 'active' ? 'disabled' : 'active'
    try {
      await toggleTenantStatus(tenant.id, targetStatus)
      message.success(targetStatus === 'disabled' ? '租户已禁用' : '租户已恢复')
      fetchData()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleRoleChange = async (userId: string, newRole: string) => {
    if (!id) return
    try {
      await updateMemberRole(id, userId, { role: newRole })
      message.success('角色更新成功')
      setEditingMemberId(null)
      fetchMembers()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleRemoveMember = async (userId: string) => {
    if (!id) return
    try {
      await removeMember(id, userId)
      message.success('成员已移除')
      fetchMembers()
      fetchData()
    } catch {
      // interceptor handles error toast
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
        <Spin spinning tip="加载中..." />
      </div>
    )
  }

  if (!tenant) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <p style={{ color: '#999' }}>租户不存在或已被删除</p>
        <Link to="/admin/tenants">返回租户列表</Link>
      </div>
    )
  }

  const gpuPercent =
    usage && tenant.gpuLimit > 0 ? Math.round((usage.gpuUsed / tenant.gpuLimit) * 100) : 0
  const cpuPercent =
    usage && parseK8sQuantity(tenant.cpuLimit) > 0
      ? Math.round((parseK8sQuantity(usage.cpuUsed) / parseK8sQuantity(tenant.cpuLimit)) * 100)
      : 0
  const memPercent =
    usage && parseK8sQuantity(tenant.memoryLimit) > 0
      ? Math.round(
          (parseK8sQuantity(usage.memoryUsed) / parseK8sQuantity(tenant.memoryLimit)) * 100,
        )
      : 0

  const memberColumns = [
    {
      title: '用户名',
      dataIndex: 'username',
      width: 100,
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      width: 160,
      ellipsis: true,
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 120,
      render: (role: string, record: TenantMember) =>
        editingMemberId === record.id ? (
          <Select
            size="small"
            value={role}
            options={ROLE_OPTIONS}
            onChange={(val) => handleRoleChange(record.id, val)}
            onBlur={() => setEditingMemberId(null)}
            style={{ width: 120 }}
            autoFocus
          />
        ) : (
          <Tag color={ROLE_COLORS[role]}>{ROLE_LABELS[role] || role}</Tag>
        ),
    },
    {
      title: '操作',
      width: 100,
      render: (_: unknown, record: TenantMember) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => setEditingMemberId(record.id)}>
            角色
          </Button>
          <Popconfirm
            title="确认移除该成员？"
            onConfirm={() => handleRemoveMember(record.id)}
            okText="确认"
            cancelText="取消"
          >
            <Button type="link" size="small" danger>
              移除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const auditColumns: ProColumns<AuditLog>[] = [
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
      width: 120,
      fieldProps: { placeholder: '搜索用户名' },
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
      title: 'IP 地址',
      dataIndex: 'ipAddress',
      width: 140,
      hideInSearch: true,
    },
  ]

  return (
    <div style={{ padding: '0 0 24px' }}>
      <Breadcrumb
        items={[
          { title: <Link to="/admin/tenants">租户管理</Link> },
          { title: tenant.displayName },
        ]}
        style={{ marginBottom: 16 }}
      />

      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>{tenant.displayName}</h2>
        <Tag color={STATUS_COLORS[tenant.status]}>
          {STATUS_LABELS[tenant.status] || tenant.status}
        </Tag>
        <Space style={{ marginLeft: 'auto' }}>
          <Button onClick={() => setEditDrawerOpen(true)}>编辑</Button>
          <Popconfirm
            title={tenant.status === 'active' ? '确认禁用该租户？' : '确认恢复该租户？'}
            onConfirm={handleToggleStatus}
            okText="确认"
            cancelText="取消"
          >
            <Button danger={tenant.status === 'active'}>
              {tenant.status === 'active' ? '禁用' : '恢复'}
            </Button>
          </Popconfirm>
        </Space>
      </div>

      <Row gutter={24}>
        <Col span={16}>
          <Descriptions
            bordered
            size="small"
            column={2}
            style={{ marginBottom: 24 }}
            title="基本信息"
          >
            <Descriptions.Item label="租户名称">{tenant.name}</Descriptions.Item>
            <Descriptions.Item label="显示名称">{tenant.displayName}</Descriptions.Item>
            <Descriptions.Item label="描述" span={2}>
              {tenant.description || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="K8s Namespace">
              {tenant.k8sNamespaceName || '-'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">{tenant.createdAt}</Descriptions.Item>
          </Descriptions>

          <div
            style={{
              marginBottom: 8,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <h3 style={{ margin: 0 }}>配额信息</h3>
            <Button size="small" onClick={() => setQuotaDrawerOpen(true)}>
              编辑配额
            </Button>
          </div>
          {usage && (
            <div style={{ marginBottom: 24 }}>
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <div>
                  <span style={{ display: 'inline-block', width: 80 }}>GPU：</span>
                  <Progress
                    percent={gpuPercent}
                    size="small"
                    style={{ width: 200, marginRight: 8 }}
                  />
                  <span>
                    {usage.gpuUsed} / {tenant.gpuLimit} 张
                  </span>
                </div>
                <div>
                  <span style={{ display: 'inline-block', width: 80 }}>CPU：</span>
                  <Progress
                    percent={cpuPercent}
                    size="small"
                    style={{ width: 200, marginRight: 8 }}
                  />
                  <span>
                    {formatQuotaValue(usage.cpuUsed)} / {formatQuotaValue(tenant.cpuLimit)} 核
                  </span>
                </div>
                <div>
                  <span style={{ display: 'inline-block', width: 80 }}>内存：</span>
                  <Progress
                    percent={memPercent}
                    size="small"
                    style={{ width: 200, marginRight: 8 }}
                  />
                  <span>
                    {formatQuotaValue(usage.memoryUsed)} / {formatQuotaValue(tenant.memoryLimit)}
                  </span>
                </div>
              </Space>
            </div>
          )}
        </Col>

        <Col span={8}>
          <div
            style={{
              marginBottom: 8,
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}
          >
            <h3 style={{ margin: 0 }}>成员管理</h3>
            <Button
              size="small"
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setInviteModalOpen(true)}
            >
              邀请
            </Button>
          </div>
          <Table
            columns={memberColumns}
            dataSource={members}
            rowKey="id"
            loading={membersLoading}
            pagination={false}
            size="small"
            scroll={{ y: 320 }}
          />
        </Col>
      </Row>

      <Row style={{ marginTop: 24 }}>
        <Col span={24}>
          <h3 style={{ marginBottom: 12 }}>审计日志</h3>
          <ProTable<AuditLog>
            columns={auditColumns}
            actionRef={auditActionRef}
            request={async (params) => {
              const { current, pageSize, action, resourceType, username, startTime, endTime } =
                params
              const res = await getAuditLogs({
                page: current,
                pageSize,
                tenantId: id,
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
            search={{ filterType: 'light', span: 8 }}
            pagination={{ defaultPageSize: 10, showSizeChanger: true }}
          />
        </Col>
      </Row>

      <Drawer
        title="编辑租户"
        open={editDrawerOpen}
        onClose={() => setEditDrawerOpen(false)}
        width={480}
        destroyOnClose
      >
        <TenantEditForm tenant={tenant} onFinish={handleEdit} />
      </Drawer>

      <Drawer
        title={`配额管理 - ${tenant.displayName}`}
        open={quotaDrawerOpen}
        onClose={() => setQuotaDrawerOpen(false)}
        width={480}
        destroyOnClose
      >
        <QuotaEditor
          tenant={tenant}
          onSuccess={() => {
            setQuotaDrawerOpen(false)
            fetchData()
          }}
        />
      </Drawer>

      <Modal
        title="邀请成员"
        open={inviteModalOpen}
        onCancel={() => setInviteModalOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <InviteMemberModal
          tenantId={tenant.id}
          onSuccess={() => {
            fetchMembers()
            fetchData()
          }}
        />
      </Modal>
    </div>
  )
}
