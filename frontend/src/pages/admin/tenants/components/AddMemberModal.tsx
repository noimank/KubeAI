import { useState } from 'react'
import { Button, Input, Select, Table } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { getMessageInstance } from '@/utils/messageHolder'
import { getUsers } from '@/services/users'
import { addMember } from '@/services/tenants'
import type { UserDetail } from '@/types/user'

const ROLE_OPTIONS = [
  { label: '算法工程师', value: 'engineer' },
  { label: 'MLOps', value: 'mlops' },
  { label: '标注员', value: 'annotator' },
]

interface Props {
  tenantId: string
  onSuccess?: () => void
}

export default function AddMemberModal({ tenantId, onSuccess }: Props) {
  const [search, setSearch] = useState('')
  const [users, setUsers] = useState<UserDetail[]>([])
  const [loading, setLoading] = useState(false)
  const [selectedUserId, setSelectedUserId] = useState<string | null>(null)
  const [selectedRole, setSelectedRole] = useState('engineer')
  const [submitting, setSubmitting] = useState(false)

  const handleSearch = async () => {
    const keyword = search.trim()
    if (!keyword) return
    setLoading(true)
    try {
      const res = await getUsers(1, 20, keyword, keyword)
      if (res.success) {
        const available = (res.data?.items || []).filter((u) => !u.tenantId)
        setUsers(available)
        setSelectedUserId(null)
        if (available.length === 0) {
          getMessageInstance()?.info('没有找到可添加的用户（无租户的用户）')
        }
      }
    } catch {
      // interceptor handles error toast
    } finally {
      setLoading(false)
    }
  }

  const handleAdd = async () => {
    if (!selectedUserId) {
      getMessageInstance()?.warning('请先选择要添加的用户')
      return
    }
    setSubmitting(true)
    try {
      await addMember(tenantId, { userId: selectedUserId, role: selectedRole })
      getMessageInstance()?.success('成员添加成功')
      onSuccess?.()
    } catch {
      // interceptor handles error toast
    } finally {
      setSubmitting(false)
    }
  }

  const columns: ColumnsType<UserDetail> = [
    { title: '用户名', dataIndex: 'username', width: 120 },
    { title: '邮箱', dataIndex: 'email', width: 200 },
    {
      title: '当前角色',
      dataIndex: 'role',
      width: 100,
    },
  ]

  return (
    <div style={{ padding: '8px 0' }}>
      <Input.Search
        placeholder="输入用户名或邮箱搜索"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onSearch={handleSearch}
        enterButton="搜索"
        loading={loading}
        style={{ marginBottom: 16 }}
      />

      {users.length > 0 && (
        <Table
          columns={columns}
          dataSource={users}
          rowKey="id"
          size="small"
          pagination={false}
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedUserId ? [selectedUserId] : [],
            onChange: (keys) => setSelectedUserId(keys[0] as string),
          }}
          style={{ marginBottom: 16 }}
        />
      )}

      {selectedUserId && (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 12 }}>
          <span>指定角色：</span>
          <Select
            value={selectedRole}
            onChange={setSelectedRole}
            options={ROLE_OPTIONS}
            style={{ width: 140 }}
          />
          <Button type="primary" loading={submitting} onClick={handleAdd}>
            添加成员
          </Button>
        </div>
      )}
    </div>
  )
}
