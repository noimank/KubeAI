import { useCallback, useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Breadcrumb, Button, Descriptions, Drawer, Space, Spin, Table, Tag, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getModel, getModelVersionFiles, getModelFileDownloadUrl } from '@/services/models'
import { formatDate, formatFileSize } from '@/utils/format'
import { getMessageInstance } from '@/utils/messageHolder'
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
  const queryClient = useQueryClient()
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [activeVersion, setActiveVersion] = useState<ModelVersion | null>(null)

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

  const handleViewFiles = useCallback((version: ModelVersion) => {
    setActiveVersion(version)
    setDrawerOpen(true)
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
      width: 100,
      render: (_: unknown, record: ModelVersion) => {
        if (record.status === 'available') {
          return (
            <Button type="link" size="small" onClick={() => handleViewFiles(record)}>
              查看文件
            </Button>
          )
        }
        if (record.status === 'uploading') {
          return (
            <Button type="link" size="small" disabled>
              上传中
            </Button>
          )
        }
        return (
          <Button type="link" size="small" disabled>
            上传失败
          </Button>
        )
      },
    },
  ]

  return (
    <div>
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[{ title: <Link to="/models">模型仓库</Link> }, { title: model.name }]}
      />
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
      render: (date?: string) => (date ? formatDate(date) : '-'),
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
