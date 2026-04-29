import { useRef, useState } from 'react'
import { Button, Modal, Tag, message } from 'antd'
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons'
import { ProTable } from '@ant-design/pro-components'
import type { ActionType, ProColumns } from '@ant-design/pro-components'
import TenantCreateForm from './components/TenantCreateForm'
import { getTenants, createTenant } from '@/services/tenants'
import type { Tenant } from '@/types/tenant'

const STATUS_COLORS: Record<string, string> = {
  active: 'green',
  disabled: 'red',
}

const STATUS_LABELS: Record<string, string> = {
  active: '正常',
  disabled: '已禁用',
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
]

export default function TenantsPage() {
  const [createModalOpen, setCreateModalOpen] = useState(false)
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
    </>
  )
}
