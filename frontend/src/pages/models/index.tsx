import { useState, useCallback } from 'react'
import { Button, Empty, Input, Popconfirm, Skeleton, Space, Table, Tag, Tooltip } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { PlusOutlined, SearchOutlined, ThunderboltOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getModels, deleteModel } from '@/services/models'
import { formatDate } from '@/utils/format'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import type { RegisteredModel } from '@/types/model'
import UploadModal from './upload-modal'
import DeployModal from './deploy-modal'

export default function ModelsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')
  const [uploadModalOpen, setUploadModalOpen] = useState(false)

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('models:write')
  const canManage = hasPermission('models:manage')
  const canDeploy = hasPermission('inference_services:write')

  const [deployModelId, setDeployModelId] = useState<string | null>(null)

  const { data, isPending, isFetching } = useQuery({
    queryKey: ['models', page, pageSize, keyword],
    queryFn: () => getModels({ current: page, pageSize, search: keyword }),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteModel,
    onSuccess: () => {
      getMessageInstance()?.success('模型已删除')
      queryClient.invalidateQueries({ queryKey: ['models'] })
    },
  })

  const handleDelete = async (id: string) => {
    try {
      await deleteMutation.mutateAsync(id)
    } catch {
      // interceptor handles error toast
    }
  }

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const columns: ColumnsType<RegisteredModel> = [
    {
      title: '名称',
      dataIndex: 'name',
      ellipsis: true,
      render: (name: string, record: RegisteredModel) => (
        <Link to={`/models/${record.id}`}>{name}</Link>
      ),
    },
    {
      title: '版本数',
      dataIndex: 'versionCount',
      width: 80,
      render: (count: number) => <Tag>{count}</Tag>,
    },
    {
      title: '模型描述',
      ellipsis: true,
      render: (_: unknown, record: RegisteredModel) => record.description || '-',
    },
    {
      title: '最新版本时间',
      width: 180,
      render: (_: unknown, record: RegisteredModel) => formatDate(record.latestVersion?.createdAt),
    },
    {
      title: '来源训练任务',
      width: 160,
      render: (_: unknown, record: RegisteredModel) => record.latestVersion?.trainingJobName || '-',
    },
    {
      title: '操作',
      width: canManage ? 240 : 160,
      render: (_: unknown, record: RegisteredModel) => {
        const deployBtn = (
          <Button
            type="link"
            size="small"
            icon={<ThunderboltOutlined />}
            disabled={!canDeploy}
            onClick={() => setDeployModelId(record.id)}
          >
            部署
          </Button>
        )
        return (
          <Space>
            <Link to={`/models/${record.id}`}>
              <Button type="link" size="small">
                查看详情
              </Button>
            </Link>
            {canDeploy ? (
              deployBtn
            ) : (
              <Tooltip title="需要 inference_services:write 权限">
                <span>{deployBtn}</span>
              </Tooltip>
            )}
            {canManage && (
              <Popconfirm
                title={`确定删除模型 "${record.name}" 吗？`}
                description="该模型的所有版本和文件将被永久删除"
                onConfirm={() => handleDelete(record.id)}
                okText="确认删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button type="link" size="small" danger loading={deleteMutation.isPending}>
                  删除
                </Button>
              </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  const emptyContent = (
    <Empty
      description="模型仓库为空，可通过本地上传或训练任务自动归档来添加模型"
      image={Empty.PRESENTED_IMAGE_SIMPLE}
    >
      <Link to="/training-jobs/create">
        <Button type="primary">新建训练任务</Button>
      </Link>
    </Empty>
  )

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Input.Search
          placeholder="搜索模型名称"
          allowClear
          style={{ width: 280 }}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={handleSearch}
          prefix={<SearchOutlined />}
        />
        {canWrite && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadModalOpen(true)}>
            本地上传
          </Button>
        )}
      </div>
      {isPending ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : (
        <Table<RegisteredModel>
          rowKey="id"
          columns={columns}
          dataSource={data?.items}
          loading={isFetching}
          pagination={{
            current: page,
            pageSize,
            total: data?.total ?? 0,
            showSizeChanger: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (total) => `共 ${total} 条`,
          }}
          onChange={handleTableChange}
          locale={{ emptyText: emptyContent }}
        />
      )}
      <UploadModal
        open={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        onSuccess={(version) => {
          setUploadModalOpen(false)
          queryClient.invalidateQueries({ queryKey: ['models'] })
          navigate(`/models/${version.registeredModelId}`)
        }}
      />
      <DeployModal
        open={!!deployModelId}
        modelId={deployModelId ?? ''}
        onClose={() => setDeployModelId(null)}
        onSuccess={(result) => {
          setDeployModelId(null)
          navigate(`/inference/${result.id}`, { state: { authToken: result.authToken } })
        }}
      />
    </div>
  )
}
