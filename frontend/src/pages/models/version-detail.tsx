import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Descriptions, Divider, Drawer, Space, Spin, Table, Tag } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery } from '@tanstack/react-query'
import LineageFlow from '@/components/LineageFlow'
import type { LineageNode } from '@/components/LineageFlow'
import { getModelVersionFiles, getModelFileDownloadUrl } from '@/services/models'
import { formatDate, formatFileSize } from '@/utils/format'
import { getMessageInstance } from '@/utils/messageHolder'
import type { ModelVersion, ModelVersionFile } from '@/types/model'

const VERSION_STATUS_MAP: Record<string, { color: string; text: string }> = {
  uploading: { color: 'processing', text: '上传中' },
  available: { color: 'success', text: '可用' },
  failed: { color: 'error', text: '上传失败' },
}

function buildLineageNodes(version: ModelVersion, modelName: string): LineageNode[] {
  return [
    {
      type: 'dataset',
      label: version.datasetName ?? '未知数据集',
      subLabel: version.datasetVersionNumber ? `v${version.datasetVersionNumber}` : undefined,
      link: version.datasetId ? `/datasets/${version.datasetId}` : undefined,
      status: version.datasetId ? 'completed' : 'pending',
    },
    {
      type: 'training',
      label: version.trainingJobName ?? '未知训练任务',
      link: version.trainingJobId ? `/training-jobs/${version.trainingJobId}` : undefined,
      status: version.trainingJobId ? 'completed' : 'pending',
    },
    {
      type: 'model',
      label: `${modelName} v${version.versionNumber}`,
      status: 'completed',
    },
    {
      type: 'inference',
      label: '推理服务',
      status: 'pending',
    },
  ]
}

function LineageSection({ version, modelName }: { version: ModelVersion; modelName: string }) {
  const nodes = buildLineageNodes(version, modelName)
  return (
    <div>
      <strong style={{ marginBottom: 8, display: 'block' }}>溯源链路</strong>
      <LineageFlow nodes={nodes} />
    </div>
  )
}

function BasicInfoSection({ version }: { version: ModelVersion }) {
  const statusCfg = VERSION_STATUS_MAP[version.status] || { color: 'default', text: version.status }
  return (
    <Descriptions bordered size="small" column={2}>
      <Descriptions.Item label="状态">
        <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
      </Descriptions.Item>
      <Descriptions.Item label="文件数">{version.fileCount}</Descriptions.Item>
      <Descriptions.Item label="大小">{formatFileSize(version.totalSizeBytes)}</Descriptions.Item>
      <Descriptions.Item label="创建时间">{formatDate(version.createdAt)}</Descriptions.Item>
    </Descriptions>
  )
}

function TrainingInfoSection({ version }: { version: ModelVersion }) {
  const hyperparams = version.hyperparameters
  const columns: ColumnsType<{ key: string; value: string }> = [
    { title: '参数名', dataIndex: 'key', width: 200 },
    { title: '参数值', dataIndex: 'value' },
  ]
  const hyperparamRows = hyperparams
    ? Object.entries(hyperparams).map(([k, v]) => ({ key: k, value: v }))
    : []

  return (
    <div>
      <Descriptions bordered size="small" column={1}>
        <Descriptions.Item label="训练任务">
          {version.trainingJobId ? (
            <Link to={`/training-jobs/${version.trainingJobId}`}>
              {version.trainingJobName ?? '-'}
            </Link>
          ) : (
            '-'
          )}
        </Descriptions.Item>
        <Descriptions.Item label="训练镜像">
          {version.imageName && version.imageTag ? (
            <Space>
              <span>{version.imageName}</span>
              <Tag>{version.imageTag}</Tag>
            </Space>
          ) : (
            '-'
          )}
        </Descriptions.Item>
      </Descriptions>
      {hyperparamRows.length > 0 && (
        <Table<{ key: string; value: string }>
          rowKey="key"
          columns={columns}
          dataSource={hyperparamRows}
          pagination={false}
          size="small"
          title={() => <strong>超参数</strong>}
          style={{ marginTop: 12 }}
        />
      )}
    </div>
  )
}

function DatasetInfoSection({ version }: { version: ModelVersion }) {
  return (
    <Descriptions bordered size="small" column={1}>
      <Descriptions.Item label="关联数据集">
        {version.datasetId ? (
          <Link to={`/datasets/${version.datasetId}`}>{version.datasetName ?? '-'}</Link>
        ) : (
          '-'
        )}
      </Descriptions.Item>
      <Descriptions.Item label="数据集版本">
        {version.datasetVersionNumber != null ? `v${version.datasetVersionNumber}` : '-'}
      </Descriptions.Item>
    </Descriptions>
  )
}

export default function VersionDetailDrawer({
  modelId,
  modelName,
  version,
  open,
  onClose,
}: {
  modelId: string
  modelName: string
  version: ModelVersion | null
  open: boolean
  onClose: () => void
}) {
  const [showFiles, setShowFiles] = useState(false)

  const { data: files = [], isLoading: filesLoading } = useQuery({
    queryKey: ['model-version-files', modelId, version?.id],
    queryFn: () => getModelVersionFiles(modelId, version!.id),
    enabled: showFiles && open && !!version && version.status === 'available',
  })

  const handleDownload = async (file: ModelVersionFile) => {
    try {
      const url = await getModelFileDownloadUrl(modelId, version!.id, file.fileName)
      window.open(url, '_blank')
    } catch {
      getMessageInstance()?.error('获取下载链接失败')
    }
  }

  const fileColumns: ColumnsType<ModelVersionFile> = [
    { title: '文件名', dataIndex: 'fileName', ellipsis: true },
    {
      title: '大小',
      dataIndex: 'sizeBytes',
      width: 100,
      render: (bytes: number) => formatFileSize(bytes),
    },
    { title: '类型', dataIndex: 'contentType', width: 160, ellipsis: true },
    {
      title: '修改时间',
      dataIndex: 'lastModified',
      width: 160,
      render: (date?: string) => (date ? formatDate(date) : '-'),
    },
    {
      title: '操作',
      width: 70,
      render: (_: unknown, file: ModelVersionFile) => (
        <Button type="link" size="small" onClick={() => handleDownload(file)}>
          下载
        </Button>
      ),
    },
  ]

  if (!version) return null

  return (
    <Drawer
      title={`v${version.versionNumber} 版本详情`}
      open={open}
      onClose={() => {
        setShowFiles(false)
        onClose()
      }}
      width={720}
    >
      <LineageSection version={version} modelName={modelName} />
      <Divider />
      <div>
        <strong style={{ display: 'block', marginBottom: 8 }}>基本信息</strong>
        <BasicInfoSection version={version} />
      </div>
      <Divider />
      <div>
        <strong style={{ display: 'block', marginBottom: 8 }}>训练信息</strong>
        <TrainingInfoSection version={version} />
      </div>
      <Divider />
      <div>
        <strong style={{ display: 'block', marginBottom: 8 }}>数据集信息</strong>
        <DatasetInfoSection version={version} />
      </div>
      <Divider />
      <div>
        {!showFiles ? (
          version.status === 'available' && (
            <Button type="primary" onClick={() => setShowFiles(true)}>
              查看文件
            </Button>
          )
        ) : (
          <div>
            <strong style={{ display: 'block', marginBottom: 8 }}>文件列表</strong>
            {filesLoading ? (
              <Spin />
            ) : (
              <Table<ModelVersionFile>
                rowKey="fileName"
                columns={fileColumns}
                dataSource={files}
                pagination={false}
                size="small"
              />
            )}
          </div>
        )}
      </div>
    </Drawer>
  )
}
