import { useCallback, useEffect, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  Breadcrumb,
  Button,
  Descriptions,
  Drawer,
  Popconfirm,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
} from 'antd'
import { PlusOutlined, ThunderboltOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getModel,
  getModelVersionFiles,
  getModelFileDownloadUrl,
  deleteModelVersion,
  deleteModel,
} from '@/services/models'
import { formatDate, formatFileSize } from '@/utils/format'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import VersionDetailDrawer from './version-detail'
import UploadModal from './upload-modal'
import DeployModal from './deploy-modal'
import type { ModelVersion, ModelVersionFile } from '@/types/model'

const VERSION_STATUS_MAP: Record<string, { color: string; text: string }> = {
  uploading: { color: 'processing', text: '上传中' },
  available: { color: 'success', text: '可用' },
  failed: { color: 'error', text: '上传失败' },
}

function formatHyperparamsTags(params?: Record<string, string> | null) {
  if (!params || Object.keys(params).length === 0) return '-'
  const entries = Object.entries(params)
  const visible = entries.slice(0, 5)
  const rest = entries.slice(5)
  return (
    <Space size={[4, 4]} wrap>
      {visible.map(([k, v]) => (
        <Tag key={k}>
          {k}={v}
        </Tag>
      ))}
      {rest.length > 0 && (
        <Tooltip title={rest.map(([k, v]) => `${k}=${v}`).join(', ')}>
          <Tag>+{rest.length}</Tag>
        </Tooltip>
      )}
    </Space>
  )
}

export default function ModelDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('models:write')
  const canManage = hasPermission('models:manage')
  const canDeploy = hasPermission('inference_services:write')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [activeVersion, setActiveVersion] = useState<ModelVersion | null>(null)
  const [detailDrawerOpen, setDetailDrawerOpen] = useState(false)
  const [selectedVersion, setSelectedVersion] = useState<ModelVersion | null>(null)
  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [deployModalOpen, setDeployModalOpen] = useState(false)

  const { data: model, isLoading } = useQuery({
    queryKey: ['model', id],
    queryFn: () => getModel(id!),
    enabled: !!id,
  })

  const hasUploading = model?.versions.some((v) => v.status === 'uploading')

  // Auto-refresh while any version is uploading
  useEffect(() => {
    if (!hasUploading) return
    const timer = setInterval(() => {
      queryClient.invalidateQueries({ queryKey: ['model', id] })
    }, 5000)
    return () => clearInterval(timer)
  }, [hasUploading, id, queryClient])

  const deleteVersionMutation = useMutation({
    mutationFn: (versionId: string) => deleteModelVersion(id!, versionId),
    onSuccess: () => {
      getMessageInstance()?.success('版本已删除')
      queryClient.invalidateQueries({ queryKey: ['model', id] })
    },
  })

  const deleteModelMutation = useMutation({
    mutationFn: () => deleteModel(id!),
    onSuccess: () => {
      getMessageInstance()?.success('模型已删除')
      navigate('/models')
    },
  })

  const handleDeleteVersion = async (versionId: string) => {
    try {
      await deleteVersionMutation.mutateAsync(versionId)
    } catch {
      // interceptor handles error toast
    }
  }

  const handleDeleteModel = async () => {
    try {
      await deleteModelMutation.mutateAsync()
    } catch {
      // interceptor handles error toast
    }
  }

  const handleViewFiles = useCallback((version: ModelVersion) => {
    setActiveVersion(version)
    setDrawerOpen(true)
  }, [])

  const handleViewDetail = useCallback((version: ModelVersion) => {
    setSelectedVersion(version)
    setDetailDrawerOpen(true)
  }, [])

  const handleFileDownload = useCallback(
    async (version: ModelVersion, file: ModelVersionFile) => {
      try {
        const url = await getModelFileDownloadUrl(id!, version.id, file.fileName)
        window.open(url, '_blank')
      } catch {
        getMessageInstance()?.error('获取下载链接失败')
      }
    },
    [id],
  )

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
        <Spin />
      </div>
    )
  }

  if (!model) return null

  const versionColumns: ColumnsType<ModelVersion> = [
    {
      title: '版本号',
      dataIndex: 'versionNumber',
      width: 100,
      render: (n: number) => `v${n}`,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (status: string) => {
        const cfg = VERSION_STATUS_MAP[status] || { color: 'default', text: status }
        return <Tag color={cfg.color}>{cfg.text}</Tag>
      },
    },
    {
      title: '训练任务',
      width: 160,
      render: (_: unknown, record: ModelVersion) => record.trainingJobName || '-',
    },
    {
      title: '训练参数',
      width: 260,
      render: (_: unknown, record: ModelVersion) => formatHyperparamsTags(record.hyperparameters),
    },
    {
      title: '文件数',
      dataIndex: 'fileCount',
      width: 80,
    },
    {
      title: '大小',
      dataIndex: 'totalSizeBytes',
      width: 100,
      render: (bytes: number) => formatFileSize(bytes),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
      render: (date: string) => formatDate(date),
    },
    {
      title: '操作',
      width: canManage ? 210 : 150,
      render: (_: unknown, record: ModelVersion) => {
        const viewDetail = (
          <Button type="link" size="small" onClick={() => handleViewDetail(record)}>
            查看详情
          </Button>
        )
        const fileAction =
          record.status === 'available' ? (
            <Button type="link" size="small" onClick={() => handleViewFiles(record)}>
              查看文件
            </Button>
          ) : (
            <Button type="link" size="small" disabled>
              {record.status === 'uploading' ? '上传中' : '上传失败'}
            </Button>
          )
        const deleteAction = canManage ? (
          <Popconfirm
            title={`确定删除版本 v${record.versionNumber} 吗？`}
            description="该版本的文件将被永久删除"
            onConfirm={() => handleDeleteVersion(record.id)}
            okText="确认删除"
            cancelText="取消"
            okButtonProps={{ danger: true }}
          >
            <Button type="link" size="small" danger loading={deleteVersionMutation.isPending}>
              删除
            </Button>
          </Popconfirm>
        ) : null
        return (
          <Space>
            {viewDetail}
            {fileAction}
            {deleteAction}
          </Space>
        )
      },
    },
  ]

  return (
    <div>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 16,
        }}
      >
        <Breadcrumb
          items={[{ title: <Link to="/models">模型仓库</Link> }, { title: model.name }]}
        />
        <Space>
          {canManage && (
            <Popconfirm
              title={`确定删除模型 "${model.name}" 吗？`}
              description="所有版本和文件将被永久删除，此操作不可撤销"
              onConfirm={handleDeleteModel}
              okText="确认删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button danger loading={deleteModelMutation.isPending}>
                删除模型
              </Button>
            </Popconfirm>
          )}
          {(() => {
            const latestAvailable = [...(model.versions ?? [])]
              .reverse()
              .find((v) => v.status === 'available')
            const deployBtn = (
              <Button
                icon={<ThunderboltOutlined />}
                disabled={!canDeploy}
                onClick={() => setDeployModalOpen(true)}
              >
                部署为推理服务
              </Button>
            )
            if (!canDeploy) {
              return (
                <Tooltip title="需要 inference_services:write 权限">
                  <span>{deployBtn}</span>
                </Tooltip>
              )
            }
            if (!latestAvailable) {
              return (
                <Tooltip title="模型当前无可用版本，弹窗内将提示无法部署">
                  <span>{deployBtn}</span>
                </Tooltip>
              )
            }
            return deployBtn
          })()}
          {canWrite ? (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadModalOpen(true)}>
              上传模型
            </Button>
          ) : (
            <Tooltip title="需要 models:write 权限（mlops 及以上角色）">
              <Button type="primary" icon={<PlusOutlined />} disabled>
                上传模型
              </Button>
            </Tooltip>
          )}
        </Space>
      </div>
      <Descriptions bordered size="small" column={2} style={{ marginBottom: 24 }}>
        <Descriptions.Item label="名称">{model.name}</Descriptions.Item>
        <Descriptions.Item label="版本数">{model.versionCount}</Descriptions.Item>
        {model.description && (
          <Descriptions.Item label="描述" span={2}>
            {model.description}
          </Descriptions.Item>
        )}
        <Descriptions.Item label="创建时间">{formatDate(model.createdAt)}</Descriptions.Item>
        <Descriptions.Item label="更新时间">{formatDate(model.updatedAt)}</Descriptions.Item>
      </Descriptions>
      <Table<ModelVersion>
        rowKey="id"
        columns={versionColumns}
        dataSource={model.versions}
        pagination={false}
        title={() => <strong>版本列表</strong>}
      />
      <FileListDrawer
        modelId={id!}
        version={activeVersion}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onDownload={handleFileDownload}
      />
      <VersionDetailDrawer
        modelId={id!}
        modelName={model.name}
        version={selectedVersion}
        open={detailDrawerOpen}
        onClose={() => setDetailDrawerOpen(false)}
      />
      <UploadModal
        open={uploadModalOpen}
        onClose={() => setUploadModalOpen(false)}
        modelId={id}
        modelName={model.name}
        onSuccess={(version) => {
          setUploadModalOpen(false)
          queryClient.invalidateQueries({ queryKey: ['model', id] })
          // Open the new version in detail drawer
          setSelectedVersion(version)
          setDetailDrawerOpen(true)
        }}
      />
      {(() => {
        const latestAvailable = [...(model.versions ?? [])]
          .reverse()
          .find((v) => v.status === 'available')
        return (
          <DeployModal
            open={deployModalOpen}
            modelId={id!}
            defaultVersionId={latestAvailable?.id}
            onClose={() => setDeployModalOpen(false)}
            onSuccess={(result) => {
              setDeployModalOpen(false)
              navigate(`/inference/${result.id}`, { state: { authToken: result.authToken } })
            }}
          />
        )
      })()}
    </div>
  )
}

function FileListDrawer({
  modelId,
  version,
  open,
  onClose,
  onDownload,
}: {
  modelId: string
  version: ModelVersion | null
  open: boolean
  onClose: () => void
  onDownload: (version: ModelVersion, file: ModelVersionFile) => void
}) {
  const { data: files = [], isLoading } = useQuery({
    queryKey: ['model-version-files', modelId, version?.id],
    queryFn: () => getModelVersionFiles(modelId, version!.id),
    enabled: open && !!version,
  })

  const columns: ColumnsType<ModelVersionFile> = [
    {
      title: '文件名',
      dataIndex: 'fileName',
      ellipsis: true,
    },
    {
      title: '大小',
      dataIndex: 'sizeBytes',
      width: 120,
      render: (bytes: number) => formatFileSize(bytes),
    },
    {
      title: '类型',
      dataIndex: 'contentType',
      width: 180,
      ellipsis: true,
    },
    {
      title: '修改时间',
      dataIndex: 'lastModified',
      width: 180,
      render: (date?: string) => formatDate(date),
    },
    {
      title: '操作',
      width: 80,
      render: (_: unknown, file: ModelVersionFile) => (
        <Button type="link" size="small" onClick={() => version && onDownload(version, file)}>
          下载
        </Button>
      ),
    },
  ]

  return (
    <Drawer
      title={version ? `v${version.versionNumber} 文件列表` : '文件列表'}
      open={open}
      onClose={onClose}
      width={720}
    >
      <Table<ModelVersionFile>
        rowKey="fileName"
        columns={columns}
        dataSource={files}
        loading={isLoading}
        pagination={false}
        size="small"
      />
    </Drawer>
  )
}
