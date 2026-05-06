import { useState, useEffect, useMemo } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  Alert,
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Empty,
  Image,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Upload,
} from 'antd'
import {
  DownloadOutlined,
  FileOutlined,
  FileImageOutlined,
  FilePdfOutlined,
  FileTextOutlined,
  FileZipOutlined,
  FileExcelOutlined,
  PlusOutlined,
  UploadOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useRbacStore } from '@/stores/rbacStore'
import { getMessageInstance } from '@/utils/messageHolder'
import { formatFileSize } from '@/utils/format'
import {
  getDatasetDetail,
  deleteDataset,
  createDatasetVersion,
  deleteDatasetVersion,
  uploadVersionFiles,
  getVersionFiles,
  getVersionStats,
  getFileDownloadUrl,
  mountDatasetVersion,
  getDatasetMountInfo,
  unmountDatasetVersion,
} from '@/services/datasets'
import type { DatasetVersion, VersionFile, DatasetMountInfo } from '@/types/dataset'

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'ico'])

const FILE_TYPE_ICONS: Record<string, React.ReactNode> = {
  pdf: <FilePdfOutlined style={{ color: '#f5222d' }} />,
  zip: <FileZipOutlined style={{ color: '#fa8c16' }} />,
  gz: <FileZipOutlined style={{ color: '#fa8c16' }} />,
  tar: <FileZipOutlined style={{ color: '#fa8c16' }} />,
  rar: <FileZipOutlined style={{ color: '#fa8c16' }} />,
  '7z': <FileZipOutlined style={{ color: '#fa8c16' }} />,
  xls: <FileExcelOutlined style={{ color: '#52c41a' }} />,
  xlsx: <FileExcelOutlined style={{ color: '#52c41a' }} />,
  csv: <FileExcelOutlined style={{ color: '#52c41a' }} />,
  txt: <FileTextOutlined style={{ color: '#8c8c8c' }} />,
  md: <FileTextOutlined style={{ color: '#8c8c8c' }} />,
  json: <FileTextOutlined style={{ color: '#1890ff' }} />,
  xml: <FileTextOutlined style={{ color: '#1890ff' }} />,
  yaml: <FileTextOutlined style={{ color: '#1890ff' }} />,
  yml: <FileTextOutlined style={{ color: '#1890ff' }} />,
  log: <FileTextOutlined style={{ color: '#8c8c8c' }} />,
}

function getFileExtension(fileName: string): string {
  return fileName.split('.').pop()?.toLowerCase() || ''
}

function isImageFile(fileName: string): boolean {
  return IMAGE_EXTENSIONS.has(getFileExtension(fileName))
}

function getFileIcon(fileName: string): React.ReactNode {
  const ext = getFileExtension(fileName)
  if (isImageFile(fileName)) return <FileImageOutlined style={{ color: '#eb2f96' }} />
  return FILE_TYPE_ICONS[ext] || <FileOutlined style={{ color: '#bfbfbf' }} />
}

function getContentTypeLabel(contentType: string): string {
  if (!contentType) return '未知'
  const known: Record<string, string> = {
    'application/octet-stream': '二进制文件',
    'application/pdf': 'PDF',
    'application/zip': 'ZIP',
    'application/x-gzip': 'GZIP',
    'application/x-tar': 'TAR',
    'application/json': 'JSON',
    'application/xml': 'XML',
    'text/plain': '文本',
    'text/csv': 'CSV',
    'text/html': 'HTML',
    'text/markdown': 'Markdown',
    'image/jpeg': 'JPEG',
    'image/png': 'PNG',
    'image/gif': 'GIF',
    'image/webp': 'WebP',
    'image/svg+xml': 'SVG',
    'image/bmp': 'BMP',
  }
  return known[contentType] || contentType
}

export default function DatasetDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('datasets:write')
  const canManage = hasPermission('datasets:manage')

  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [newVersionDesc, setNewVersionDesc] = useState('')
  const [uploadingVersionId, setUploadingVersionId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedVersionId, setSelectedVersionId] = useState<string | undefined>()
  const [mountInfoMap, setMountInfoMap] = useState<Record<string, DatasetMountInfo>>({})
  const [mountingVersionId, setMountingVersionId] = useState<string | null>(null)
  const [imageUrls, setImageUrls] = useState<Record<string, string>>({})

  const {
    data: detailRes,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['dataset-detail', id],
    queryFn: () => getDatasetDetail(id!),
    enabled: !!id,
  })

  const dataset = detailRes?.data

  const versions: DatasetVersion[] = useMemo(() => dataset?.versions || [], [dataset])

  const latestVersionId = versions.length > 0 ? versions[versions.length - 1].id : undefined
  const effectiveVersionId = selectedVersionId || latestVersionId

  const {
    data: filesData,
    isLoading: filesLoading,
    error: filesError,
  } = useQuery({
    queryKey: ['version-files', id, effectiveVersionId],
    queryFn: () => getVersionFiles(id!, effectiveVersionId!),
    enabled: !!effectiveVersionId && activeTab === 'preview',
    retry: 1,
  })

  const { data: statsData, error: statsError } = useQuery({
    queryKey: ['version-stats', id, effectiveVersionId],
    queryFn: () => getVersionStats(id!, effectiveVersionId!),
    enabled: !!effectiveVersionId && activeTab === 'preview',
    retry: 1,
  })

  const files: VersionFile[] = useMemo(() => filesData || [], [filesData])

  // 批量获取图片缩略图 URL（限制并发，逐批请求）
  useEffect(() => {
    if (!files.length || !id || !effectiveVersionId) return

    const imageFiles = files.filter((f) => isImageFile(f.fileName))
    if (!imageFiles.length) {
      setImageUrls({})
      return
    }

    let cancelled = false
    const BATCH_SIZE = 5
    const batches: (typeof imageFiles)[] = []
    for (let i = 0; i < imageFiles.length; i += BATCH_SIZE) {
      batches.push(imageFiles.slice(i, i + BATCH_SIZE))
    }

    async function loadBatch(batchIdx: number) {
      if (cancelled || batchIdx >= batches.length) return
      const batch = batches[batchIdx]
      const results = await Promise.allSettled(
        batch.map(async (f) => {
          const url = await getFileDownloadUrl(id!, effectiveVersionId!, f.fileName)
          return { fileName: f.fileName, url }
        }),
      )
      if (cancelled) return
      const partial: Record<string, string> = {}
      for (const r of results) {
        if (r.status === 'fulfilled') {
          partial[r.value.fileName] = r.value.url
        }
      }
      setImageUrls((prev) => ({ ...prev, ...partial }))
      await loadBatch(batchIdx + 1)
    }

    loadBatch(0)

    return () => {
      cancelled = true
    }
  }, [files, id, effectiveVersionId])

  // 版本列表 Tab 挂载状态持久化
  useEffect(() => {
    if (activeTab !== 'versions' || !versions.length || !id) return

    let cancelled = false
    Promise.all(
      versions.map(async (v) => {
        const info = await getDatasetMountInfo(id!, v.id)
        return { versionId: v.id, info }
      }),
    ).then((results) => {
      if (cancelled) return
      const map: Record<string, DatasetMountInfo> = {}
      for (const r of results) {
        if (r.info) {
          map[r.versionId] = r.info
        }
      }
      setMountInfoMap(map)
    })

    return () => {
      cancelled = true
    }
  }, [activeTab, versions, id])

  const deleteDatasetMutation = useMutation({
    mutationFn: () => deleteDataset(id!),
    onSuccess: () => {
      getMessageInstance()?.success('数据集删除成功')
      navigate('/datasets')
    },
  })

  const createVersionMutation = useMutation({
    mutationFn: (description?: string) => createDatasetVersion(id!, description),
    onSuccess: () => {
      getMessageInstance()?.success('版本创建成功')
      setCreateModalOpen(false)
      setNewVersionDesc('')
      queryClient.invalidateQueries({ queryKey: ['dataset-detail', id] })
    },
  })

  const deleteVersionMutation = useMutation({
    mutationFn: (versionId: string) => deleteDatasetVersion(id!, versionId),
    onSuccess: () => {
      getMessageInstance()?.success('版本删除成功')
      queryClient.invalidateQueries({ queryKey: ['dataset-detail', id] })
    },
  })

  const uploadMutation = useMutation({
    mutationFn: ({ versionId, files }: { versionId: string; files: File[] }) =>
      uploadVersionFiles(id!, versionId, files),
    onSuccess: () => {
      getMessageInstance()?.success('文件上传成功')
      setUploadingVersionId(null)
      queryClient.invalidateQueries({ queryKey: ['dataset-detail', id] })
    },
  })

  const downloadMutation = useMutation({
    mutationFn: (fileName: string) => getFileDownloadUrl(id!, effectiveVersionId!, fileName),
    onSuccess: (url) => {
      window.open(url, '_blank')
    },
  })

  const mountMutation = useMutation({
    mutationFn: (versionId: string) => mountDatasetVersion(id!, versionId),
    onSuccess: (info, versionId) => {
      getMessageInstance()?.success('挂载成功')
      setMountInfoMap((prev) => ({ ...prev, [versionId]: info }))
      setMountingVersionId(null)
    },
    onError: () => {
      setMountingVersionId(null)
    },
  })

  const unmountMutation = useMutation({
    mutationFn: (versionId: string) => unmountDatasetVersion(id!, versionId),
    onSuccess: (_, versionId) => {
      getMessageInstance()?.success('卸载成功')
      setMountInfoMap((prev) => {
        const next = { ...prev }
        delete next[versionId]
        return next
      })
    },
  })

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
        <Spin spinning tip="加载中...">
          <div />
        </Spin>
      </div>
    )
  }

  if (error || !dataset) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <p style={{ color: 'var(--text-tertiary)' }}>数据集不存在或已被删除</p>
        <Link to="/datasets">返回数据集列表</Link>
      </div>
    )
  }

  const versionColumns: ColumnsType<DatasetVersion> = [
    {
      title: '版本号',
      dataIndex: 'versionNumber',
      width: 100,
      render: (val: number) => `v${val}`,
    },
    {
      title: '描述',
      dataIndex: 'description',
      ellipsis: true,
      render: (val: string | undefined) => val || '-',
    },
    {
      title: '文件数',
      dataIndex: 'fileCount',
      width: 80,
    },
    {
      title: '大小',
      dataIndex: 'totalSizeBytes',
      width: 120,
      render: (val: number) => formatFileSize(val),
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 180,
    },
    {
      title: '挂载状态',
      width: 100,
      render: (_, record) => {
        const info = mountInfoMap[record.id]
        return info ? <Tag color="green">已挂载</Tag> : <Tag>未挂载</Tag>
      },
    },
    {
      title: '操作',
      width: 240,
      render: (_, record) => {
        const info = mountInfoMap[record.id]
        return (
          <Space size="small">
            {hasPermission('datasets:read') && !info && (
              <Button
                type="link"
                size="small"
                loading={mountMutation.isPending && mountingVersionId === record.id}
                onClick={() => {
                  setMountingVersionId(record.id)
                  mountMutation.mutate(record.id)
                }}
              >
                挂载
              </Button>
            )}
            {info && (
              <>
                <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{info.pvcName}</span>
                {canManage && (
                  <Popconfirm
                    title="确认卸载？"
                    description="卸载后 PVC 将被删除，正在使用的任务可能受影响。"
                    onConfirm={() => unmountMutation.mutate(record.id)}
                    okText="确认"
                    cancelText="取消"
                  >
                    <Button type="link" size="small" danger>
                      卸载
                    </Button>
                  </Popconfirm>
                )}
              </>
            )}
            {canWrite && (
              <Upload
                multiple
                showUploadList={false}
                beforeUpload={(file, fileList) => {
                  if (file !== fileList[0]) return false
                  uploadMutation.mutate({ versionId: record.id, files: [...fileList] })
                  return false
                }}
              >
                <Button
                  type="link"
                  size="small"
                  icon={<UploadOutlined />}
                  loading={uploadMutation.isPending && uploadingVersionId === record.id}
                  onClick={() => setUploadingVersionId(record.id)}
                >
                  上传文件
                </Button>
              </Upload>
            )}
            {canManage && (
              <Popconfirm
                title="确认删除该版本？"
                description="删除后，版本内的所有文件将被永久清除。"
                onConfirm={() => deleteVersionMutation.mutate(record.id)}
                okText="确认"
                cancelText="取消"
              >
                <Button type="link" size="small" danger>
                  删除
                </Button>
              </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  const fileColumns: ColumnsType<VersionFile> = [
    {
      title: '文件名',
      dataIndex: 'fileName',
      ellipsis: true,
      render: (val: string) => {
        if (isImageFile(val) && imageUrls[val]) {
          return (
            <Space>
              <Image
                src={imageUrls[val]}
                width={36}
                height={36}
                style={{ objectFit: 'cover', borderRadius: 4 }}
                preview={false}
                placeholder
                fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzYiIGhlaWdodD0iMzYiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjM2IiBoZWlnaHQ9IjM2IiBmaWxsPSIjZjBmMGYwIi8+PC9zdmc+"
              />
              <span>{val}</span>
            </Space>
          )
        }
        return (
          <Space>
            {getFileIcon(val)}
            <span>{val}</span>
          </Space>
        )
      },
    },
    {
      title: '大小',
      dataIndex: 'sizeBytes',
      width: 110,
      render: (val: number) => formatFileSize(val),
    },
    {
      title: '类型',
      dataIndex: 'contentType',
      width: 140,
      ellipsis: true,
      render: (val: string) => (
        <Tooltip title={val}>
          <span>{getContentTypeLabel(val)}</span>
        </Tooltip>
      ),
    },
    {
      title: '最后修改时间',
      dataIndex: 'lastModified',
      width: 190,
      render: (val?: string) => (val ? new Date(val).toLocaleString('zh-CN') : '-'),
    },
    {
      title: '操作',
      width: 80,
      render: (_, record) => (
        <Button
          type="link"
          size="small"
          icon={<DownloadOutlined />}
          loading={downloadMutation.isPending}
          onClick={() => downloadMutation.mutate(record.fileName)}
        >
          下载
        </Button>
      ),
    },
  ]

  return (
    <div style={{ padding: 0 }}>
      <Breadcrumb
        items={[{ title: <Link to="/datasets">数据集</Link> }, { title: dataset.name }]}
        style={{ marginBottom: 16 }}
      />

      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 12 }}>
        <h2 style={{ margin: 0 }}>{dataset.name}</h2>
        <Space style={{ marginLeft: 'auto' }}>
          {canWrite && (
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
              创建新版本
            </Button>
          )}
          {canManage && (
            <Popconfirm
              title="确认删除该数据集？"
              description="删除后，所有版本和文件将被永久清除，此操作不可恢复。"
              onConfirm={() => deleteDatasetMutation.mutate()}
              okText="确认"
              cancelText="取消"
            >
              <Button danger loading={deleteDatasetMutation.isPending}>
                删除数据集
              </Button>
            </Popconfirm>
          )}
        </Space>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'overview',
            label: '概览',
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <Card size="small">
                  <Descriptions bordered size="small" column={2}>
                    <Descriptions.Item label="名称">{dataset.name}</Descriptions.Item>
                    <Descriptions.Item label="创建人">
                      {dataset.createdByName || '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label="描述" span={2}>
                      {dataset.description || '-'}
                    </Descriptions.Item>
                    <Descriptions.Item label="创建时间">{dataset.createdAt}</Descriptions.Item>
                    <Descriptions.Item label="更新时间">{dataset.updatedAt}</Descriptions.Item>
                  </Descriptions>
                </Card>
                <Card size="small">
                  <Space size="large">
                    <Statistic title="版本数" value={dataset.versionCount} />
                    <Statistic title="文件数" value={dataset.totalFileCount} />
                    <Statistic title="总大小" value={formatFileSize(dataset.totalSizeBytes)} />
                  </Space>
                </Card>
              </Space>
            ),
          },
          {
            key: 'versions',
            label: '版本列表',
            children: (
              <Table<DatasetVersion>
                rowKey="id"
                columns={versionColumns}
                dataSource={versions}
                pagination={false}
                size="small"
              />
            ),
          },
          {
            key: 'preview',
            label: '预览',
            children: (
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                <Card size="small">
                  <Space size="large" align="center">
                    <span>版本选择：</span>
                    <Select
                      value={effectiveVersionId}
                      onChange={setSelectedVersionId}
                      style={{ width: 200 }}
                      options={versions.map((v) => ({
                        value: v.id,
                        label: `v${v.versionNumber}`,
                      }))}
                    />
                    {statsData && (
                      <>
                        <Statistic title="文件数" value={statsData.fileCount} />
                        <Statistic
                          title="总大小"
                          value={formatFileSize(statsData.totalSizeBytes)}
                        />
                        <Statistic
                          title="文件类型数"
                          value={statsData.fileTypeDistribution.length}
                        />
                      </>
                    )}
                  </Space>
                </Card>

                {statsError && (
                  <Alert type="warning" message="统计数据加载失败，请稍后重试" showIcon closable />
                )}

                {statsData && statsData.fileTypeDistribution.length > 0 && (
                  <Card size="small">
                    <span style={{ marginRight: 8 }}>文件类型分布：</span>
                    {statsData.fileTypeDistribution.map((d) => (
                      <Tag key={d.extension}>
                        {d.extension}({d.count})
                      </Tag>
                    ))}
                  </Card>
                )}

                {filesError ? (
                  <Alert
                    type="error"
                    message="文件列表加载失败"
                    description="无法获取文件列表，可能是存储服务暂时不可用。请刷新页面重试。"
                    showIcon
                  />
                ) : (
                  <Spin spinning={filesLoading}>
                    {files.length > 0 ? (
                      <Table<VersionFile>
                        rowKey="fileName"
                        columns={fileColumns}
                        dataSource={files}
                        pagination={false}
                        size="small"
                      />
                    ) : (
                      !filesLoading && <Empty description="暂无文件，请先上传文件" />
                    )}
                  </Spin>
                )}
              </Space>
            ),
          },
        ]}
      />

      <Modal
        title="创建新版本"
        open={createModalOpen}
        onCancel={() => {
          setCreateModalOpen(false)
          setNewVersionDesc('')
        }}
        onOk={() => createVersionMutation.mutate(newVersionDesc || undefined)}
        confirmLoading={createVersionMutation.isPending}
        okText="创建"
        cancelText="取消"
        destroyOnHidden
      >
        <Input.TextArea
          placeholder="版本描述（可选）"
          value={newVersionDesc}
          onChange={(e) => setNewVersionDesc(e.target.value)}
          rows={3}
          style={{ marginTop: 16 }}
        />
      </Modal>
    </div>
  )
}
