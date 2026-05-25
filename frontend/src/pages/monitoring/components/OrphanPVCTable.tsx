import { useState } from 'react'
import { Button, Popconfirm, Table, message } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { cleanupPVCs } from '@/services/monitoring'
import type { OrphanPVC } from '@/types/monitoring'

interface Props {
  data: OrphanPVC[]
  loading: boolean
  onRefresh: () => void
}

export default function OrphanPVCTable({ data, loading, onRefresh }: Props) {
  const [selectedKeys, setSelectedKeys] = useState<string[]>([])
  const [cleaning, setCleaning] = useState(false)

  const selectedItems = data.filter((item) =>
    selectedKeys.includes(`${item.namespace}/${item.name}`),
  )

  const handleCleanup = async () => {
    setCleaning(true)
    try {
      const items = selectedItems.map((item) => [item.namespace, item.name] as [string, string])
      const res = await cleanupPVCs(items)
      if (res.success) {
        message.success(
          `清理完成：成功 ${res.data?.cleanedCount ?? 0} 个，失败 ${res.data?.failedCount ?? 0} 个`,
        )
        setSelectedKeys([])
        onRefresh()
      } else {
        message.error(res.message || '清理失败')
      }
    } catch {
      message.error('清理请求失败')
    } finally {
      setCleaning(false)
    }
  }

  const columns: ColumnsType<OrphanPVC> = [
    { title: 'PVC 名称', dataIndex: 'name', key: 'name', ellipsis: true },
    { title: '命名空间', dataIndex: 'namespace', key: 'namespace', ellipsis: true },
    { title: '存储大小', dataIndex: 'storage', key: 'storage', width: 120 },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      key: 'createdAt',
      width: 180,
      render: (v: string | null) => (v ? new Date(v).toLocaleString('zh-CN') : '-'),
    },
    { title: '孤立原因', dataIndex: 'orphanReason', key: 'orphanReason', ellipsis: true },
  ]

  return (
    <>
      {selectedKeys.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Popconfirm
            title={`确认删除 ${selectedKeys.length} 个孤立 PVC？`}
            description="删除后数据将无法恢复"
            onConfirm={handleCleanup}
            okText="确认删除"
            cancelText="取消"
          >
            <Button danger loading={cleaning}>
              批量删除 ({selectedKeys.length})
            </Button>
          </Popconfirm>
        </div>
      )}
      <Table<OrphanPVC>
        columns={columns}
        dataSource={data}
        loading={loading}
        rowKey={(record) => `${record.namespace}/${record.name}`}
        size="small"
        pagination={false}
        locale={{ emptyText: '暂无孤立 PVC' }}
        rowSelection={{
          selectedRowKeys: selectedKeys,
          onChange: (keys) => setSelectedKeys(keys as string[]),
        }}
      />
    </>
  )
}
