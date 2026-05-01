import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
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
  message,
  Upload,
} from 'antd'
import { DownloadOutlined, PlusOutlined, UploadOutlined } from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useRbacStore } from '@/stores/rbacStore'
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
} from '@/services/datasets'
import type { DatasetVersion, VersionFile } from '@/types/dataset'

const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg'])

function isImageFile(fileName: string): boolean {
  const ext = fileName.split('.').pop()?.toLowerCase() || ''
  return IMAGE_EXTENSIONS.has(ext)
}

export default function DatasetDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canManage = hasPermission('datasets:manage')

  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [newVersionDesc, setNewVersionDesc] = useState('')
  const [uploadingVersionId, setUploadingVersionId] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('overview')
  const [selectedVersionId, setSelectedVersionId] = useState<string | undefined>()

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

  const versions: DatasetVersion[] = dataset?.versions || []

  // 默认选中最新版本
  const latestVersionId = versions.length > 0 ? versions[versions.length - 1].id : undefined
  const effectiveVersionId = selectedVersionId || latestVersionId

  const { data: filesData, isLoading: filesLoading } = useQuery({
    queryKey: ['version-files', id, effectiveVersionId],
    queryFn: () => getVersionFiles(id!, effectiveVersionId!),
    enabled: !!effectiveVersionId && activeTab === 'preview',
  })

  const { data: statsData } = useQuery({
    queryKey: ['version-stats', id, effectiveVersionId],
    queryFn: () => getVersionStats(id!, effectiveVersionId!),
    enabled: !!effectiveVersionId && activeTab === 'preview',
  })

  const files: VersionFile[] = filesData || []

  const deleteDatasetMutation = useMutation({
    mutationFn: () => deleteDataset(id!),
    onSuccess: () => {
      message.success('数据集删除成功')
      navigate('/datasets')
    },
  })

  const createVersionMutation = useMutation({
    mutationFn: (description?: string) => createDatasetVersion(id!, description),
    onSuccess: () => {
      message.success('版本创建成功')
      setCreateModalOpen(false)
      setNewVersionDesc('')
      queryClient.invalidateQueries({ queryKey: ['dataset-detail', id] })
    },
  })

  const deleteVersionMutation = useMutation({
    mutationFn: (versionId: string) => deleteDatasetVersion(id!, versionId),
    onSuccess: () => {
      message.success('版本删除成功')
      queryClient.invalidateQueries({ queryKey: ['dataset-detail', id] })
    },
  })

  const uploadMutation = useMutation({
    mutationFn: ({ versionId, files }: { versionId: string; files: File[] }) =>
      uploadVersionFiles(id!, versionId, files),
    onSuccess: () => {
      message.success('文件上传成功')
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

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 400 }}>
        <Spin spinning tip="加载中..." />
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
      title: '操作',
      width: 160,
      render: (_, record) => (
        <Space size="small">
          {canManage && (
            <Upload
              showUploadList={false}
              beforeUpload={(file) => {
                uploadMutation.mutate({ versionId: record.id, files: [file] })
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
      ),
    },
  ]

  const fileColumns: ColumnsType<VersionFile> = [
    {
      title: '文件名',
      dataIndex: 'fileName',
      ellipsis: true,
      render: (val: string) => {
        if (isImageFile(val)) {
          return (
            <Space>
              <Image
                src={undefined}
                width={50}
                height={50}
                style={{ objectFit: 'cover', borderRadius: 4 }}
                preview={false}
                placeholder
                fallback="data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNTAiIGhlaWdodD0iNTAiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PHJlY3Qgd2lkdGg9IjUwIiBoZWlnaHQ9IjUwIiBmaWxsPSIjZjBmMGYwIi8+PC9zdmc+"
              />
              {val}
            </Space>
          )
        }
        return val
      },
    },
    {
      title: '大小',
      dataIndex: 'sizeBytes',
      width: 120,
      render: (val: number) => formatFileSize(val),
    },
    {
      title: '类型',
      dataIndex: 'contentType',
      width: 160,
      ellipsis: true,
    },
    {
      title: '最后修改时间',
      dataIndex: 'lastModified',
      width: 200,
      render: (val: string) => (val ? new Date(val).toLocaleString('zh-CN') : '-'),
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
        {canManage && (
          <Space style={{ marginLeft: 'auto' }}>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModalOpen(true)}>
              创建新版本
            </Button>
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
          </Space>
        )}
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
