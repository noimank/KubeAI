import { useRef, useState } from 'react'
import {
  Button,
  Descriptions,
  Drawer,
  Form,
  Modal,
  Popconfirm,
  Select,
  Space,
  Tag,
  message,
} from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { ProTable } from '@ant-design/pro-components'
import type { ActionType, ProColumns } from '@ant-design/pro-components'
import { getUsers, getUser, updateUser, toggleUserStatus, deleteUser } from '@/services/users'
import { getTenants } from '@/services/tenants'
import type { UserDetail, UserRole } from '@/types/user'
import type { Tenant } from '@/types/tenant'

const ROLE_COLORS: Record<string, string> = {
  admin: 'red',
  mlops: 'blue',
  engineer: 'green',
  annotator: 'orange',
}

const ROLE_LABELS: Record<string, string> = {
  admin: '管理员',
  mlops: 'MLOps 工程师',
  engineer: '算法工程师',
  annotator: '标注员',
}

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

function getUserStatus(user: UserDetail): string {
  if (!user.isActive) return 'disabled'
  if (user.lockedUntil && new Date(user.lockedUntil) > new Date()) return 'locked'
  return 'active'
}

export default function UsersPage() {
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<UserDetail | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailUser, setDetailUser] = useState<UserDetail | null>(null)
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [form] = Form.useForm()
  const actionRef = useRef<ActionType>(null)

  const loadTenants = async () => {
    try {
      const res = await getTenants(1, 200)
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
    form.setFieldsValue({
      role: record.role,
      tenantId: record.tenantId ?? undefined,
    })
    setEditModalOpen(true)
    loadTenants()
  }

  const handleEdit = async (values: { role: UserRole; tenantId?: string }) => {
    if (!editingUser) return
    try {
      await updateUser(editingUser.id, values)
      message.success('用户更新成功')
      setEditModalOpen(false)
      setEditingUser(null)
      actionRef.current?.reload()
    } catch {
      // interceptor handles error
    }
  }

  const handleToggleStatus = async (record: UserDetail) => {
    try {
      await toggleUserStatus(record.id, { isActive: !record.isActive })
      message.success(record.isActive ? '用户已禁用' : '用户已启用')
      actionRef.current?.reload()
    } catch {
      // interceptor handles error
    }
  }

  const handleDelete = async (record: UserDetail) => {
    try {
      await deleteUser(record.id)
      message.success('用户删除成功')
      actionRef.current?.reload()
    } catch {
      // interceptor handles error
    }
  }

  const columns: ProColumns<UserDetail>[] = [
    {
      title: '用户名',
      dataIndex: 'username',
      width: 140,
      fieldProps: { placeholder: '请输入用户名' },
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
      valueType: 'select',
      fieldProps: {
        placeholder: '请选择角色',
        options: [
          { value: 'admin', label: '管理员' },
          { value: 'mlops', label: 'MLOps 工程师' },
          { value: 'engineer', label: '算法工程师' },
          { value: 'annotator', label: '标注员' },
        ],
      },
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
      valueType: 'select',
      fieldProps: {
        placeholder: '请选择状态',
        options: [
          { value: 'true', label: '正常' },
          { value: 'false', label: '已禁用' },
        ],
      },
      render: (_, record) => {
        const status = getUserStatus(record)
        return <Tag color={STATUS_COLORS[status]}>{STATUS_LABELS[status]}</Tag>
      },
    },
    {
      title: '注册时间',
      dataIndex: 'createdAt',
      valueType: 'dateTimeRange',
      width: 180,
      render: (_, record) => new Date(record.createdAt).toLocaleString(),
      fieldProps: { placeholder: ['开始时间', '结束时间'] },
    },
    {
      title: '操作',
      valueType: 'option',
      width: 260,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => openDetail(record)}>
            详情
          </Button>
          <Button type="link" size="small" onClick={() => openEdit(record)}>
            编辑
          </Button>
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
        </Space>
      ),
    },
  ]

  return (
    <>
      <ProTable<UserDetail>
        columns={columns}
        actionRef={actionRef}
        request={async (params) => {
          const [startTime, endTime] = (params.createdAt as [string, string] | undefined) ?? []
          const res = await getUsers(
            params.current,
            params.pageSize,
            params.username || undefined,
            params.email || undefined,
            params.role || undefined,
            params.isActive != null && params.isActive !== ''
              ? params.isActive === 'true'
              : undefined,
            startTime || undefined,
            endTime || undefined,
          )
          return {
            data: res.data?.items || [],
            total: res.data?.total || 0,
            success: res.success,
          }
        }}
        rowKey="id"
        search={{
          filterType: 'light',
          span: {
            xs: 24,
            sm: 12,
            md: 8,
            lg: 8,
            xl: 6,
            xxl: 4,
          },
        }}
        toolBarRender={() => [
          <Button
            key="reload"
            icon={<ReloadOutlined />}
            onClick={() => actionRef.current?.reload()}
          >
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
                {new Date(detailUser.lockedUntil).toLocaleString()}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="注册时间">
              {new Date(detailUser.createdAt).toLocaleString()}
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
      >
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Form.Item name="role" label="角色" rules={[{ required: true }]}>
            <Select
              options={[
                { value: 'admin', label: '管理员' },
                { value: 'mlops', label: 'MLOps 工程师' },
                { value: 'engineer', label: '算法工程师' },
                { value: 'annotator', label: '标注员' },
              ]}
            />
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
