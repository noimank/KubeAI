import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { Breadcrumb, Card, Descriptions, Spin, Tabs, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { getImage, getBuildLog } from '@/services/images'

const BUILD_STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'warning', text: '排队中' },
  building: { color: 'processing', text: '构建中' },
  pushing: { color: 'processing', text: '推送中' },
  succeeded: { color: 'success', text: '成功' },
  failed: { color: 'error', text: '失败' },
}

const ACTIVE_BUILD_STATUSES = new Set<string>(['pending', 'building', 'pushing'])

export default function ImageDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [activeTab, setActiveTab] = useState('overview')

  const {
    data: image,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['image-detail', id],
    queryFn: () => getImage(id!),
    enabled: !!id,
  })

  const isCustom = image?.source === 'custom'

  const { data: logData } = useQuery({
    queryKey: ['buildLog', id],
    queryFn: () => getBuildLog(id!),
    enabled: !!id && isCustom && activeTab === 'build-log',
    refetchInterval:
      isCustom &&
      activeTab === 'build-log' &&
      image?.buildStatus &&
      ACTIVE_BUILD_STATUSES.has(image.buildStatus)
        ? 3000
        : false,
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

  if (error || !image) {
    return (
      <div style={{ textAlign: 'center', padding: 48 }}>
        <p style={{ color: 'var(--text-tertiary)' }}>镜像不存在或已被删除</p>
        <Link to="/images">返回镜像列表</Link>
      </div>
    )
  }

  const tabs = [
    {
      key: 'overview',
      label: '概览',
      children: (
        <Card size="small">
          <Descriptions bordered size="small" column={2}>
            <Descriptions.Item label="名称">{image.name}</Descriptions.Item>
            <Descriptions.Item label="标签">{image.tag}</Descriptions.Item>
            <Descriptions.Item label="镜像地址" span={2}>
              <Typography.Text copyable={{ tooltips: ['复制', '已复制'] }}>
                {image.imageRef}
              </Typography.Text>
            </Descriptions.Item>
            <Descriptions.Item label="来源">
              <Tag color={image.source === 'custom' ? 'purple' : 'default'}>
                {image.source === 'custom' ? '自定义' : '预置'}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="描述">{image.description || '—'}</Descriptions.Item>
            <Descriptions.Item label="启用状态">
              <Tag color={image.isEnabled ? 'success' : 'default'}>
                {image.isEnabled ? '启用' : '禁用'}
              </Tag>
            </Descriptions.Item>
            {isCustom && (
              <Descriptions.Item label="构建状态">
                {image.buildStatus ? (
                  <Tag color={BUILD_STATUS_CONFIG[image.buildStatus]?.color || 'default'}>
                    {BUILD_STATUS_CONFIG[image.buildStatus]?.text || image.buildStatus}
                  </Tag>
                ) : (
                  <Tag>—</Tag>
                )}
              </Descriptions.Item>
            )}
            <Descriptions.Item label="创建时间">{image.createdAt}</Descriptions.Item>
            <Descriptions.Item label="更新时间">{image.updatedAt}</Descriptions.Item>
          </Descriptions>
        </Card>
      ),
    },
  ]

  if (isCustom) {
    tabs.push({
      key: 'build-log',
      label: '构建日志',
      children: (
        <div>
          {image.buildStatus && (
            <div style={{ marginBottom: 12 }}>
              <Tag color={BUILD_STATUS_CONFIG[image.buildStatus]?.color || 'default'}>
                {BUILD_STATUS_CONFIG[image.buildStatus]?.text || image.buildStatus}
              </Tag>
            </div>
          )}
          <pre
            style={{
              padding: 16,
              margin: 0,
              fontSize: 13,
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
              background: 'var(--colorBgLayout, #f5f5f5)',
              borderRadius: 6,
              maxHeight: 'calc(100vh - 360px)',
              overflow: 'auto',
            }}
          >
            {logData?.log || '暂无日志'}
          </pre>
        </div>
      ),
    })

    if (image.dockerfile) {
      tabs.push({
        key: 'dockerfile',
        label: 'Dockerfile',
        children: (
          <pre
            style={{
              padding: 16,
              margin: 0,
              fontSize: 13,
              fontFamily: 'monospace',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-all',
              background: 'var(--colorBgLayout, #f5f5f5)',
              borderRadius: 6,
              lineHeight: 1.8,
            }}
          >
            {image.dockerfile.split('\n').map((line, i) => (
              <div key={i}>
                <span
                  style={{
                    color: 'var(--colorTextQuaternary, rgba(0,0,0,0.25))',
                    userSelect: 'none',
                    marginRight: 16,
                  }}
                >
                  {String(i + 1).padStart(3)}
                </span>
                {line}
              </div>
            ))}
          </pre>
        ),
      })
    }
  }

  return (
    <div style={{ padding: 0 }}>
      <Breadcrumb
        items={[
          { title: <Link to="/images">镜像管理</Link> },
          { title: `${image.name}:${image.tag}` },
        ]}
        style={{ marginBottom: 16 }}
      />

      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>
          {image.name}:{image.tag}
        </h2>
      </div>

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={tabs} />
    </div>
  )
}
