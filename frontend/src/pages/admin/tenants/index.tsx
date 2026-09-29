import { useState, useCallback } from 'react'
import { Button, Input, Modal, Popconfirm, Segmented, Space, Table, Tag } from 'antd'
import { Link } from 'react-router-dom'
import { PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import { formatDate } from '@/utils/format'
import TenantCreateForm from './components/TenantCreateForm'
import TenantEditForm from './components/TenantEditForm'
import QuotaEditor from './components/QuotaEditor'
import MemberList from './components/MemberList'
import InviteMemberModal from './components/InviteMemberModal'
import AddMemberModal from './components/AddMemberModal'
import {
  getTenants,
  createTenant,
  updateTenant,
  toggleTenantStatus,
  deleteTenant,
} from '@/services/tenants'
import type { Tenant, TenantUpdateRequest } from '@/types/tenant'
import { getMessageInstance } from '@/utils/messageHolder'

const STATUS_TABS = [
  { label: '全部', value: '' },
  { label: '正常', value: 'active' },
  { label: '已禁用', value: 'disabled' },
]

export default function TenantsPage() {
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [statusFilter, setStatusFilter] = useState('')
  const [keyword, setKeyword] = useState<string | undefined>(undefined)
  const [searchText, setSearchText] = useState('')
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null)
  const [deleteModalOpen, setDeleteModalOpen] = useState(false)
  const [deletingTenant, setDeletingTenant] = useState<Tenant | null>(null)
  const [quotaModalOpen, setQuotaModalOpen] = useState(false)
  const [quotaTenant, setQuotaTenant] = useState<Tenant | null>(null)
  const [memberModalOpen, setMemberModalOpen] = useState(false)
  const [memberTenant, setMemberTenant] = useState<Tenant | null>(null)
  const [inviteModalOpen, setInviteModalOpen] = useState(false)
  const [addMemberModalOpen, setAddMemberModalOpen] = useState(false)

  const {
    data: res,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['tenants', page, pageSize, statusFilter, keyword],
    queryFn: () => getTenants(page, pageSize, { status: statusFilter || undefined, keyword }),
  })

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const handleCreate = async (values: {
    name: string
    displayName: string
    description?: string
  }) => {
    await createTenant(values)
    getMessageInstance()?.success('租户创建成功')
    setCreateModalOpen(false)
    refetch()
  }

  const handleEdit = async (values: TenantUpdateRequest) => {
    if (!editingTenant) return
    try {
      await updateTenant(editingTenant.id, values)
      getMessageInstance()?.success('租户更新成功')
      setEditModalOpen(false)
      setEditingTenant(null)
      refetch()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleToggleStatus = async (record: Tenant) => {
    const targetStatus = record.status === 'active' ? 'disabled' : 'active'
    try {
      await toggleTenantStatus(record.id, targetStatus)
      getMessageInstance()?.success(targetStatus === 'disabled' ? '租户已禁用' : '租户已恢复')
      refetch()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleDelete = async () => {
    if (!deletingTenant) return
    try {
      await deleteTenant(deletingTenant.id)
      getMessageInstance()?.success('租户删除成功')
      setDeleteModalOpen(false)
      setDeletingTenant(null)
      refetch()
    } catch {
      // interceptor handles error toast
    }
  }

  const openDeleteModal = (record: Tenant) => {
    setDeletingTenant(record)
    setDeleteModalOpen(true)
  }

  const columns: ColumnsType<Tenant> = [
    {
      title: '租户名称',
      dataIndex: 'name',
      width: 160,
      fixed: 'left',
      ellipsis: true,
    },
    {
      title: '显示名称',
      dataIndex: 'displayName',
      width: 160,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (_, record) => (
        <Tag color={record.status === 'active' ? 'green' : 'red'}>
          {record.status === 'active' ? '正常' : '已禁用'}
        </Tag>
      ),
    },
    {
      title: 'GPU 配额',
      dataIndex: 'gpuLimit',
      width: 100,
      render: (_, record) => `${record.gpuLimit} 张`,
    },
    {
      title: 'CPU 配额',
      dataIndex: 'cpuLimit',
      width: 100,
      render: (_, record) => `${record.cpuLimit} 核`,
    },
    {
      title: '内存配额',
      dataIndex: 'memoryLimit',
      width: 100,
    },
    {
      title: '成员数',
      dataIndex: 'memberCount',
      width: 80,
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
      render: (v: string) => formatDate(v),
    },
    {
      title: '操作',
      width: 280,
      render: (_, record) => (
        <Space size="small">
          <Link to={`/admin/tenants/${record.id}`}>
            <Button type="link" size="small">
              详情
            </Button>
          </Link>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditingTenant(record)
              setEditModalOpen(true)
            }}
          >
            编辑
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setQuotaTenant(record)
              setQuotaModalOpen(true)
            }}
          >
            配额
          </Button>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setMemberTenant(record)
              setMemberModalOpen(true)
            }}
          >
            成员
          </Button>
          <Popconfirm
            title={record.status === 'active' ? '确认禁用该租户？' : '确认恢复该租户？'}
            description={
              record.status === 'active'
                ? '禁用后，该租户下所有成员将无法登录'
                : '恢复后，成员可恢复正常使用'
            }
            onConfirm={() => handleToggleStatus(record)}
            okText="确认"
            cancelText="取消"
          >
            <Button type="link" size="small" danger={record.status === 'active'}>
              {record.status === 'active' ? '禁用' : '恢复'}
            </Button>
          </Popconfirm>
          <Button type="link" size="small" danger onClick={() => openDeleteModal(record)}>
            删除
          </Button>
        </Space>
      ),
    },
  ]

  const canDelete = deletingTenant && deletingTenant.memberCount === 0

  return (
    <>
      <div
        style={{
          marginBottom: 16,
          display: 'flex',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <Space>
          <Segmented
            options={STATUS_TABS}
            value={statusFilter}
            onChange={(val) => {
              setStatusFilter(val as string)
              setPage(1)
            }}
          />
          <Input.Search
            placeholder="搜索租户名称"
            allowClear
            style={{ width: 280 }}
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            onSearch={handleSearch}
            prefix={<SearchOutlined />}
          />
        </Space>
        <Space>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
            创建租户
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
            刷新
          </Button>
        </Space>
      </div>

      <Table<Tenant>
        rowKey="id"
        columns={columns}
        dataSource={res?.data?.items}
        loading={isLoading}
        scroll={{ x: 1260 }}
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
                还没有租户，创建第一个租户开始吧
              </p>
              <Button
                type="primary"
                icon={<PlusOutlined />}
                onClick={() => setCreateModalOpen(true)}
              >
                创建租户
              </Button>
            </div>
          ),
        }}
      />

      <Modal
        title="创建租户"
        open={createModalOpen}
        onCancel={() => setCreateModalOpen(false)}
        footer={null}
        destroyOnHidden
      >
        <TenantCreateForm onFinish={handleCreate} />
      </Modal>

      <Modal
        title="编辑租户"
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false)
          setEditingTenant(null)
        }}
        footer={null}
        destroyOnHidden
      >
        {editingTenant && <TenantEditForm tenant={editingTenant} onFinish={handleEdit} />}
      </Modal>

      <Modal
        title="删除租户"
        open={deleteModalOpen}
        onCancel={() => {
          setDeleteModalOpen(false)
          setDeletingTenant(null)
        }}
        onOk={canDelete ? handleDelete : undefined}
        okText={canDelete ? '确认删除' : undefined}
        okButtonProps={{ danger: true }}
        footer={
          canDelete ? undefined : (
            <Button
              onClick={() => {
                setDeleteModalOpen(false)
                setDeletingTenant(null)
              }}
            >
              关闭
            </Button>
          )
        }
      >
        {canDelete ? (
          <p>
            确认删除租户「{deletingTenant.displayName}」？删除后，K8s Namespace
            及相关资源将被一并删除，此操作不可恢复。
          </p>
        ) : (
          <p>该租户下仍有成员，请先移除所有成员后再删除。</p>
        )}
      </Modal>

      <Modal
        title={`配额管理 - ${quotaTenant?.displayName ?? ''}`}
        open={quotaModalOpen}
        onCancel={() => {
          setQuotaModalOpen(false)
          setQuotaTenant(null)
        }}
        footer={null}
        destroyOnHidden
      >
        {quotaTenant && (
          <QuotaEditor
            tenant={quotaTenant}
            onSuccess={() => {
              setQuotaModalOpen(false)
              setQuotaTenant(null)
              refetch()
            }}
          />
        )}
      </Modal>

      <Modal
        title={`成员管理 - ${memberTenant?.displayName ?? ''}`}
        open={memberModalOpen}
        onCancel={() => {
          setMemberModalOpen(false)
          setMemberTenant(null)
        }}
        footer={null}
        destroyOnHidden
        width={800}
      >
        {memberTenant && (
          <div>
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
              <Button onClick={() => setAddMemberModalOpen(true)}>添加成员</Button>
              <Button type="primary" onClick={() => setInviteModalOpen(true)}>
                邀请成员
              </Button>
            </div>
            <MemberList tenantId={memberTenant.id} />
          </div>
        )}
      </Modal>

      <Modal
        title="邀请成员"
        open={inviteModalOpen}
        onCancel={() => setInviteModalOpen(false)}
        footer={null}
        destroyOnHidden
      >
        {memberTenant && (
          <InviteMemberModal tenantId={memberTenant.id} onSuccess={() => refetch()} />
        )}
      </Modal>

      <Modal
        title="添加成员"
        open={addMemberModalOpen}
        onCancel={() => setAddMemberModalOpen(false)}
        footer={null}
        destroyOnHidden
        width={640}
      >
        {memberTenant && (
          <AddMemberModal
            tenantId={memberTenant.id}
            onSuccess={() => {
              setAddMemberModalOpen(false)
              refetch()
            }}
          />
        )}
      </Modal>
    </>
  )
}
