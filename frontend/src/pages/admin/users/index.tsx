import { useState, useCallback } from 'react'
import {
  Button,
  DatePicker,
  Descriptions,
  Drawer,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import { ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import type { Dayjs } from 'dayjs'
import { getUsers, getUser, updateUser, toggleUserStatus, deleteUser } from '@/services/users'
import { getTenants } from '@/services/tenants'
import { getMessageInstance } from '@/utils/messageHolder'
import { formatDate } from '@/utils/format'
import { useAuthStore } from '@/stores/authStore'
import type { UserDetail, UserRole } from '@/types/user'
import type { Tenant } from '@/types/tenant'
import {
  ROLE_LABELS,
  ROLE_COLORS,
  ROLE_OPTIONS_WITH_ADMIN as ROLE_OPTIONS,
} from '@/utils/roleLabels'

const STATUS_COLORS: Record<string, string> = {
  active: 'green',
  disabled: 'red',
  locked: 'orange',
}

const STATUS_LABELS: Record<string, string> = {
  active: '正常',
  disabled: '已禁用',
  locked: '已锁定',
}

const ACTIVE_OPTIONS = [
  { value: 'true', label: '正常' },
  { value: 'false', label: '已禁用' },
]

function getUserStatus(user: UserDetail): string {
  if (!user.isActive) return 'disabled'
  if (user.lockedUntil && new Date(user.lockedUntil) > new Date()) return 'locked'
  return 'active'
}

export default function UsersPage() {
  const currentUser = useAuthStore((s) => s.user)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailUser, setDetailUser] = useState<UserDetail | null>(null)
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [form] = Form.useForm()

  const isSelf = (userId: string) => currentUser?.id === userId

  // Filter input states
  const [filterUsername, setFilterUsername] = useState<string>()
  const [filterEmail, setFilterEmail] = useState<string>()
  const [filterRole, setFilterRole] = useState<string>()
  const [filterActive, setFilterActive] = useState<string>()
  const [filterTimeRange, setFilterTimeRange] = useState<[Dayjs, Dayjs]>()

  // Committed filters
  const [filters, setFilters] = useState<{
    username?: string
    email?: string
    role?: string
    isActive?: boolean
    startTime?: string
    endTime?: string
  }>()

  const {
    data: res,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['users', page, pageSize, filters],
    queryFn: () =>
      getUsers(
        page,
        pageSize,
        filters?.username,
        filters?.email,
        filters?.role,
        filters?.isActive,
        filters?.startTime,
        filters?.endTime,
      ),
  })

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const handleSearch = () => {
    setFilters({
      username: filterUsername,
      email: filterEmail,
      role: filterRole,
      isActive: filterActive != null && filterActive !== '' ? filterActive === 'true' : undefined,
      startTime: filterTimeRange?.[0]?.toISOString(),
      endTime: filterTimeRange?.[1]?.toISOString(),
    })
    setPage(1)
  }

  const handleReset = () => {
    setFilterUsername(undefined)
    setFilterEmail(undefined)
    setFilterRole(undefined)
    setFilterActive(undefined)
    setFilterTimeRange(undefined)
    setFilters(undefined)
    setPage(1)
  }

  const loadTenants = async () => {
    try {
      const res = await getTenants(1, 100)
      setTenants(res.data?.items ?? [])
    } catch {
      // ignore
    }
  }

  const openDetail = async (record: UserDetail) => {
    try {
      const res = await getUser(record.id)
      setDetailUser(res.data ?? null)
      setDetailOpen(true)
    } catch {
      // interceptor handles error
    }
  }

  const openEdit = (record: UserDetail) => {
    setEditingUser(record)
    setEditModalOpen(true)
    loadTenants()
  }

  const handleEdit = async (values: { role: UserRole; tenantId?: string }) => {
    if (!editingUser) return
    if (isSelf(editingUser.id)) {
      getMessageInstance()?.error('不能修改自身账户的角色或租户')
      return
    }
    try {
      await updateUser(editingUser.id, values)
      getMessageInstance()?.success('用户更新成功')
      setEditModalOpen(false)
      setEditingUser(null)
      refetch()
    } catch {
      // interceptor handles error
    }
  }

  const handleToggleStatus = async (record: UserDetail) => {
    if (isSelf(record.id)) {
      getMessageInstance()?.error('不能禁用自身账户')
      return
    }
    try {
      await toggleUserStatus(record.id, { isActive: !record.isActive })
      getMessageInstance()?.success(record.isActive ? '用户已禁用' : '用户已启用')
      refetch()
    } catch {
      // interceptor handles error
    }
  }

  const handleDelete = async (record: UserDetail) => {
    if (isSelf(record.id)) {
      getMessageInstance()?.error('不能删除自身账户')
      return
    }
    try {
      await deleteUser(record.id)
      getMessageInstance()?.success('用户删除成功')
      refetch()
    } catch {
      // interceptor handles error
    }
  }

  const columns: ColumnsType<UserDetail> = [
    {
      title: '用户名',
      dataIndex: 'username',
      width: 140,
      fixed: 'left',
      ellipsis: true,
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      width: 200,
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 120,
      render: (_, record) => (
        <Tag color={ROLE_COLORS[record.role]}>{ROLE_LABELS[record.role] || record.role}</Tag>
      ),
    },
    {
      title: '所属租户',
      dataIndex: 'tenantName',
      width: 140,
      render: (_, record) => record.tenantName || '-',
    },
    {
      title: '状态',
      dataIndex: 'isActive',
      width: 100,
      render: (_, record) => {
        const status = getUserStatus(record)
        return <Tag color={STATUS_COLORS[status]}>{STATUS_LABELS[status]}</Tag>
      },
    },
    {
      title: '注册时间',
      dataIndex: 'createdAt',
      width: 180,
      render: (v: string) => formatDate(v),
    },
    {
      title: '操作',
      width: 260,
      render: (_, record) => {
        const self = isSelf(record.id)
        return (
          <Space size="small">
            <Button type="link" size="small" onClick={() => openDetail(record)}>
              详情
            </Button>
            {self ? (
              <Tooltip title="不能修改自身账户">
                <Button type="link" size="small" disabled>
                  编辑
                </Button>
              </Tooltip>
            ) : (
              <Button type="link" size="small" onClick={() => openEdit(record)}>
                编辑
              </Button>
            )}
            {self ? (
              <Tooltip title="不能禁用自身账户">
                <Button type="link" size="small" danger={record.isActive} disabled>
                  {record.isActive ? '禁用' : '启用'}
                </Button>
              </Tooltip>
            ) : (
              <Popconfirm
                title={record.isActive ? '确认禁用该用户？' : '确认启用该用户？'}
                description={
                  record.isActive ? '禁用后，该用户将无法登录系统' : '启用后，用户可正常登录'
                }
                onConfirm={() => handleToggleStatus(record)}
                okText="确认"
                cancelText="取消"
              >
                <Button type="link" size="small" danger={record.isActive}>
                  {record.isActive ? '禁用' : '启用'}
                </Button>
              </Popconfirm>
            )}
            {self ? (
              <Tooltip title="不能删除自身账户">
                <Button type="link" size="small" danger disabled>
                  删除
                </Button>
              </Tooltip>
            ) : (
              <Popconfirm
                title="确认删除该用户？"
                description="删除后该用户将不再出现在用户列表中，但其关联数据会保留"
                onConfirm={() => handleDelete(record)}
                okText="确认删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button type="link" size="small" danger>
                  删除
                </Button>
              </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  return (
    <>
      <div style={{ marginBottom: 16 }}>
        <Space wrap>
          <Input
            placeholder="请输入用户名"
            value={filterUsername}
            onChange={(e) => setFilterUsername(e.target.value || undefined)}
            style={{ width: 160 }}
            prefix={<SearchOutlined />}
            onPressEnter={handleSearch}
          />
          <Input
            placeholder="请输入邮箱"
            value={filterEmail}
            onChange={(e) => setFilterEmail(e.target.value || undefined)}
            style={{ width: 200 }}
            onPressEnter={handleSearch}
          />
          <Select
            placeholder="请选择角色"
            value={filterRole}
            onChange={setFilterRole}
            options={ROLE_OPTIONS}
            style={{ width: 160 }}
            allowClear
          />
          <Select
            placeholder="请选择状态"
            value={filterActive}
            onChange={setFilterActive}
            options={ACTIVE_OPTIONS}
            style={{ width: 120 }}
            allowClear
          />
          <DatePicker.RangePicker
            value={filterTimeRange}
            onChange={(dates) => setFilterTimeRange(dates as [Dayjs, Dayjs] | undefined)}
            style={{ width: 280 }}
            placeholder={['开始时间', '结束时间']}
          />
          <Button type="primary" onClick={handleSearch}>
            查询
          </Button>
          <Button onClick={handleReset}>重置</Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
            刷新
          </Button>
        </Space>
      </div>

      <Table<UserDetail>
        rowKey="id"
        columns={columns}
        dataSource={res?.data?.items}
        loading={isLoading}
        scroll={{ x: 1140 }}
        pagination={{
          current: page,
          pageSize,
          total: res?.data?.total ?? 0,
          showSizeChanger: true,
          showTotal: (total) => `共 ${total} 条`,
        }}
        onChange={handleTableChange}
        locale={{
          emptyText: (
            <div style={{ padding: '24px 0', textAlign: 'center' }}>
              <p style={{ color: 'var(--text-tertiary)', marginBottom: 16 }}>
                还没有用户，用户注册后将在此展示
              </p>
            </div>
          ),
        }}
      />

      <Drawer
        title="用户详情"
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false)
          setDetailUser(null)
        }}
        width={520}
      >
        {detailUser && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="用户名">{detailUser.username}</Descriptions.Item>
            <Descriptions.Item label="邮箱">{detailUser.email}</Descriptions.Item>
            <Descriptions.Item label="角色">
              <Tag color={ROLE_COLORS[detailUser.role]}>{ROLE_LABELS[detailUser.role]}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="认证方式">
              {detailUser.authProvider === 'local' ? '本地认证' : 'OAuth'}
            </Descriptions.Item>
            <Descriptions.Item label="所属租户">{detailUser.tenantName || '-'}</Descriptions.Item>
            <Descriptions.Item label="账号状态">
              <Tag color={STATUS_COLORS[getUserStatus(detailUser)]}>
                {STATUS_LABELS[getUserStatus(detailUser)]}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="登录失败次数">
              {detailUser.failedLoginAttempts}
            </Descriptions.Item>
            {detailUser.lockedUntil && (
              <Descriptions.Item label="锁定至">
                {formatDate(detailUser.lockedUntil)}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="注册时间">
              {formatDate(detailUser.createdAt)}
            </Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      <Modal
        title={`编辑用户 - ${editingUser?.username ?? ''}`}
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false)
          setEditingUser(null)
        }}
        footer={null}
        destroyOnHidden
        afterOpenChange={(visible) => {
          if (!visible || !editingUser) return
          form.setFieldsValue({
            role: editingUser.role,
            tenantId: editingUser.tenantId ?? undefined,
          })
        }}
      >
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} />
          </Form.Item>
          <Form.Item name="tenantId" label="所属租户">
            <Select
              allowClear
              placeholder="选择租户"
              options={tenants.map((t) => ({ value: t.id, label: t.displayName }))}
            />
          </Form.Item>
          <Form.Item>
            <Space>
              <Button type="primary" htmlType="submit">
                保存
              </Button>
              <Button
                onClick={() => {
                  setEditModalOpen(false)
                  setEditingUser(null)
                }}
              >
                取消
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </>
  )
}
