import { useEffect, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  Breadcrumb,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Input,
  Modal,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Table,
  Tag,
} from 'antd'
import InlineLoading from '@/components/InlineLoading'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import type { Dayjs } from 'dayjs'
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
import { getMessageInstance } from '@/utils/messageHolder'
import { formatKi, parseK8sQuantity } from '@/utils/format'
import type { Tenant, TenantUpdateRequest, QuotaUsage, TenantMember } from '@/types/tenant'
import type { AuditLog, AuditAction, ResourceType } from '@/types/audit'
import {
  ACTION_LABELS,
  ACTION_COLORS,
  ACTION_OPTIONS,
  RESOURCE_LABELS,
  RESOURCE_COLORS,
  RESOURCE_OPTIONS,
} from '@/utils/auditLabels'
import { ROLE_LABELS, ROLE_COLORS, ROLE_OPTIONS } from '@/utils/roleLabels'

const STATUS_COLORS: Record<string, string> = { active: 'green', disabled: 'red' }
const STATUS_LABELS: Record<string, string> = { active: '正常', disabled: '已禁用' }

function formatQuotaValue(val: string | number): string {
  if (typeof val === 'number') return formatKi(val)
  const ki = parseK8sQuantity(val)
  if (ki > 0) return formatKi(ki)
  return String(val)
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

  // Audit log state
  const [auditPage, setAuditPage] = useState(1)
  const [auditPageSize, setAuditPageSize] = useState(10)
  const [auditTimeRange, setAuditTimeRange] = useState<[Dayjs, Dayjs]>()
  const [auditUsername, setAuditUsername] = useState<string>()
  const [auditActions, setAuditActions] = useState<AuditAction[]>()
  const [auditResourceTypes, setAuditResourceTypes] = useState<ResourceType[]>()
  const [auditFilters, setAuditFilters] = useState<{
    startTime?: string
    endTime?: string
    username?: string
    action?: AuditAction[]
    resourceType?: ResourceType[]
  }>()

  const {
    data: auditRes,
    isLoading: auditLoading,
    refetch: auditRefetch,
  } = useQuery({
    queryKey: ['audit-logs', id, auditPage, auditPageSize, auditFilters],
    queryFn: () =>
      getAuditLogs({
        page: auditPage,
        pageSize: auditPageSize,
        tenantId: id,
        startTime: auditFilters?.startTime,
        endTime: auditFilters?.endTime,
        username: auditFilters?.username,
        action: auditFilters?.action?.length ? auditFilters.action : undefined,
        resourceType: auditFilters?.resourceType?.length ? auditFilters.resourceType : undefined,
      }),
    enabled: !!id,
  })

  const handleAuditSearch = () => {
    setAuditFilters({
      startTime: auditTimeRange?.[0]?.toISOString(),
      endTime: auditTimeRange?.[1]?.toISOString(),
      username: auditUsername,
      action: auditActions,
      resourceType: auditResourceTypes,
    })
    setAuditPage(1)
  }

  const handleAuditReset = () => {
    setAuditTimeRange(undefined)
    setAuditUsername(undefined)
    setAuditActions(undefined)
    setAuditResourceTypes(undefined)
    setAuditFilters(undefined)
    setAuditPage(1)
  }

  const handleAuditTableChange = useCallback((pagination: TablePaginationConfig) => {
    setAuditPage(pagination.current || 1)
    setAuditPageSize(pagination.pageSize || 10)
  }, [])

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
      getMessageInstance()?.success('租户更新成功')
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
      getMessageInstance()?.success(targetStatus === 'disabled' ? '租户已禁用' : '租户已恢复')
      fetchData()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleRoleChange = async (userId: string, newRole: string) => {
    if (!id) return
    try {
      await updateMemberRole(id, userId, { role: newRole })
      getMessageInstance()?.success('角色更新成功')
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
      getMessageInstance()?.success('成员已移除')
      fetchMembers()
      fetchData()
    } catch {
      // interceptor handles error toast
    }
  }

  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
        <InlineLoading tip="加载中..." />
      </div>
    )
  }

  if (!tenant) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <p style={{ color: 'var(--text-tertiary)' }}>租户不存在或已被删除</p>
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

  const auditColumns: ColumnsType<AuditLog> = [
    {
      title: '操作时间',
      dataIndex: 'createdAt',
      width: 180,
    },
    {
      title: '操作人',
      dataIndex: 'username',
      width: 120,
    },
    {
      title: '操作类型',
      dataIndex: 'action',
      width: 120,
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
          <Card size="small" style={{ marginBottom: 24 }}>
            <Descriptions bordered size="small" column={2} title="基本信息">
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
          </Card>

          <Card
            size="small"
            title="配额信息"
            extra={
              <Button size="small" onClick={() => setQuotaDrawerOpen(true)}>
                编辑配额
              </Button>
            }
            style={{ marginBottom: 24 }}
          >
            {usage && (
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
            )}
          </Card>
        </Col>

        <Col span={8}>
          <Card
            size="small"
            title="成员管理"
            extra={
              <Button
                size="small"
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setInviteModalOpen(true)}
              >
                邀请
              </Button>
            }
          >
            <Table
              columns={memberColumns}
              dataSource={members}
              rowKey="id"
              loading={membersLoading}
              pagination={false}
              size="small"
              scroll={{ y: 320 }}
            />
          </Card>
        </Col>
      </Row>

      <Row style={{ marginTop: 24 }}>
        <Col span={24}>
          <Card size="small" title="审计日志">
            <div style={{ marginBottom: 16 }}>
              <Space wrap>
                <DatePicker.RangePicker
                  value={auditTimeRange}
                  onChange={(dates) => setAuditTimeRange(dates as [Dayjs, Dayjs] | undefined)}
                  style={{ width: 280 }}
                />
                <Input
                  placeholder="搜索用户名"
                  value={auditUsername}
                  onChange={(e) => setAuditUsername(e.target.value || undefined)}
                  style={{ width: 160 }}
                  prefix={<SearchOutlined />}
                  onPressEnter={handleAuditSearch}
                />
                <Select
                  mode="multiple"
                  placeholder="选择操作类型"
                  value={auditActions}
                  onChange={(v) => setAuditActions(v as AuditAction[])}
                  options={ACTION_OPTIONS}
                  style={{ minWidth: 160 }}
                  allowClear
                />
                <Select
                  mode="multiple"
                  placeholder="选择资源类型"
                  value={auditResourceTypes}
                  onChange={(v) => setAuditResourceTypes(v as ResourceType[])}
                  options={RESOURCE_OPTIONS}
                  style={{ minWidth: 160 }}
                  allowClear
                />
                <Button type="primary" onClick={handleAuditSearch}>
                  查询
                </Button>
                <Button onClick={handleAuditReset}>重置</Button>
                <Button icon={<ReloadOutlined />} onClick={() => auditRefetch()}>
                  刷新
                </Button>
              </Space>
            </div>
            <Table<AuditLog>
              rowKey="id"
              columns={auditColumns}
              dataSource={auditRes?.data?.items}
              loading={auditLoading}
              pagination={{
                current: auditPage,
                pageSize: auditPageSize,
                total: auditRes?.data?.total ?? 0,
                showSizeChanger: true,
                showTotal: (total) => `共 ${total} 条`,
              }}
              onChange={handleAuditTableChange}
            />
          </Card>
        </Col>
      </Row>

      <Drawer
        title="编辑租户"
        open={editDrawerOpen}
        onClose={() => setEditDrawerOpen(false)}
        width={480}
        destroyOnHidden
      >
        <TenantEditForm tenant={tenant} onFinish={handleEdit} />
      </Drawer>

      <Drawer
        title={`配额管理 - ${tenant.displayName}`}
        open={quotaDrawerOpen}
        onClose={() => setQuotaDrawerOpen(false)}
        width={480}
        destroyOnHidden
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
