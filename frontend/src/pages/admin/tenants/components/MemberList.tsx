import { useEffect, useState } from 'react'
import { Button, Popconfirm, Select, Space, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getMessageInstance } from '@/utils/messageHolder'
import { listMembers, removeMember, updateMemberRole } from '@/services/tenants'
import type { TenantMember } from '@/types/tenant'

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

interface Props {
  tenantId: string
}

export default function MemberList({ tenantId }: Props) {
  const [members, setMembers] = useState<TenantMember[]>([])
  const [loading, setLoading] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)

  const fetchMembers = async () => {
    setLoading(true)
    try {
      const res = await listMembers(tenantId)
      if (res.success) setMembers(res.data || [])
    } catch {
      // interceptor handles error toast
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMembers()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenantId])

  const handleRoleChange = async (userId: string, newRole: string) => {
    try {
      await updateMemberRole(tenantId, userId, { role: newRole })
      getMessageInstance()?.success('角色更新成功')
      setEditingId(null)
      fetchMembers()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleRemove = async (userId: string) => {
    try {
      await removeMember(tenantId, userId)
      getMessageInstance()?.success('成员已移除')
      fetchMembers()
    } catch {
      // interceptor handles error toast
    }
  }

  const columns: ColumnsType<TenantMember> = [
    {
      title: '用户名',
      dataIndex: 'username',
      width: 120,
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      width: 200,
    },
    {
      title: '角色',
      dataIndex: 'role',
      width: 160,
      render: (role: string, record) =>
        editingId === record.id ? (
          <Select
            size="small"
            value={role}
            options={ROLE_OPTIONS}
            onChange={(val) => handleRoleChange(record.id, val)}
            onBlur={() => setEditingId(null)}
            style={{ width: 120 }}
            autoFocus
          />
        ) : (
          <Tag color={ROLE_COLORS[role]}>{ROLE_LABELS[role] || role}</Tag>
        ),
    },
    {
      title: '状态',
      dataIndex: 'isActive',
      width: 80,
      render: (v: boolean) => (v ? <Tag color="green">正常</Tag> : <Tag color="red">禁用</Tag>),
    },
    {
      title: '加入时间',
      dataIndex: 'joinedAt',
      width: 180,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '操作',
      width: 120,
      render: (_, record) => (
        <Space size="small">
          <Button type="link" size="small" onClick={() => setEditingId(record.id)}>
            修改角色
          </Button>
          <Popconfirm
            title="确认移除该成员？"
            description="移除后该成员将失去租户访问权限，其创建的资源将保留在租户内"
            onConfirm={() => handleRemove(record.id)}
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

  return (
    <Table
      columns={columns}
      dataSource={members}
      rowKey="id"
      loading={loading}
      pagination={false}
      size="small"
    />
  )
}
