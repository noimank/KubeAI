import { useRef, useState } from 'react'
import { Button, Modal, Popconfirm, Space, Tag, message } from 'antd'
import { Link } from 'react-router-dom'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { ProTable } from '@ant-design/pro-components'
import type { ActionType, ProColumns } from '@ant-design/pro-components'
import TenantCreateForm from './components/TenantCreateForm'
import TenantEditForm from './components/TenantEditForm'
import QuotaEditor from './components/QuotaEditor'
import MemberList from './components/MemberList'
import InviteMemberModal from './components/InviteMemberModal'
import {
  getTenants,
  createTenant,
  updateTenant,
  toggleTenantStatus,
  deleteTenant,
} from '@/services/tenants'
import type { Tenant, TenantUpdateRequest } from '@/types/tenant'

const STATUS_COLORS: Record<string, string> = {
  active: 'green',
  disabled: 'red',
}

const STATUS_LABELS: Record<string, string> = {
  active: '正常',
  disabled: '已禁用',
}

export default function TenantsPage() {
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
  const actionRef = useRef<ActionType>(null)

  const handleCreate = async (values: {
    name: string
    displayName: string
    description?: string
  }) => {
    await createTenant(values)
    message.success('租户创建成功')
    setCreateModalOpen(false)
    actionRef.current?.reload()
  }

  const handleEdit = async (values: TenantUpdateRequest) => {
    if (!editingTenant) return
    try {
      await updateTenant(editingTenant.id, values)
      message.success('租户更新成功')
      setEditModalOpen(false)
      setEditingTenant(null)
      actionRef.current?.reload()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleToggleStatus = async (record: Tenant) => {
    const targetStatus = record.status === 'active' ? 'disabled' : 'active'
    try {
      await toggleTenantStatus(record.id, targetStatus)
      message.success(targetStatus === 'disabled' ? '租户已禁用' : '租户已恢复')
      actionRef.current?.reload()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleDelete = async () => {
    if (!deletingTenant) return
    try {
      await deleteTenant(deletingTenant.id)
      message.success('租户删除成功')
      setDeleteModalOpen(false)
      setDeletingTenant(null)
      actionRef.current?.reload()
    } catch {
      // interceptor handles error toast
    }
  }

  const openDeleteModal = (record: Tenant) => {
    setDeletingTenant(record)
    setDeleteModalOpen(true)
  }

  const columns: ProColumns<Tenant>[] = [
    {
      title: '租户名称',
      dataIndex: 'name',
      width: 160,
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
        <Tag color={STATUS_COLORS[record.status]}>
          {STATUS_LABELS[record.status] || record.status}
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
      valueType: 'dateTime',
      width: 180,
    },
    {
      title: '操作',
      valueType: 'option',
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
      <ProTable<Tenant>
        columns={columns}
        actionRef={actionRef}
        request={async (params) => {
          const res = await getTenants(params.current, params.pageSize)
          return {
            data: res.data?.items || [],
            total: res.data?.total || 0,
            success: res.success,
          }
        }}
        rowKey="id"
        search={false}
        toolBarRender={() => [
          <Button
            key="create"
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
          >
            创建租户
          </Button>,
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
              <p style={{ color: '#999', marginBottom: 16 }}>还没有租户，创建第一个租户开始吧</p>
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
              actionRef.current?.reload()
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
            <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'flex-end' }}>
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
          <InviteMemberModal
            tenantId={memberTenant.id}
            onSuccess={() => actionRef.current?.reload()}
          />
        )}
      </Modal>
    </>
  )
}
