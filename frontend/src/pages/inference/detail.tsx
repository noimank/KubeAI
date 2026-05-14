import { useParams } from 'react-router-dom'
import { Descriptions, Spin, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { getInferenceService } from '@/services/inference'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'warning', text: '等待中' },
  deploying: { color: 'processing', text: '部署中' },
  running: { color: 'success', text: '运行中' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

export default function InferenceServiceDetailPage() {
  const { id } = useParams<{ id: string }>()

  const { data: svc, isLoading } = useQuery({
    queryKey: ['inferenceService', id],
    queryFn: () => getInferenceService(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && ['pending', 'deploying'].includes(status) ? 5000 : false
    },
  })

  if (isLoading) return <Spin />
  if (!svc) return null

  const statusCfg = STATUS_CONFIG[svc.status] ?? { color: 'default', text: svc.status }

  return (
    <Descriptions column={2} bordered size="small" title={svc.name}>
      <Descriptions.Item label="状态">
        <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
      </Descriptions.Item>
      <Descriptions.Item label="GPU">
        {svc.gpuCount > 0 ? `${svc.gpuCount} 张` : '—'}
      </Descriptions.Item>
      <Descriptions.Item label="CPU">{svc.cpu} 核</Descriptions.Item>
      <Descriptions.Item label="内存">{svc.memory}</Descriptions.Item>
      <Descriptions.Item label="副本数">{svc.replicas}</Descriptions.Item>
      <Descriptions.Item label="推理端点">
        {svc.endpointUrl ? (
          <a href={svc.endpointUrl} target="_blank" rel="noreferrer">
            {svc.endpointUrl}
          </a>
        ) : (
          <Tag>部署后生成</Tag>
        )}
      </Descriptions.Item>
      <Descriptions.Item label="描述" span={2}>
        {svc.description || '—'}
      </Descriptions.Item>
      <Descriptions.Item label="创建时间">{svc.createdAt}</Descriptions.Item>
      <Descriptions.Item label="更新时间">{svc.updatedAt}</Descriptions.Item>
    </Descriptions>
  )
}
