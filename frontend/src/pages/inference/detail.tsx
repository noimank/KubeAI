import { useState } from 'react'
import { useParams, useLocation, useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Collapse,
  Descriptions,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Table,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { SyncOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import dayjs from 'dayjs'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import {
  getInferenceService,
  getInferenceServiceEvents,
  regenerateToken,
} from '@/services/inference'
import type { InferenceServiceEvent } from '@/types/inference'

const STATUS_CONFIG: Record<string, { color: string; text: string }> = {
  pending: { color: 'warning', text: '等待中' },
  deploying: { color: 'processing', text: '部署中' },
  running: { color: 'success', text: '运行中' },
  failed: { color: 'error', text: '已失败' },
  stopped: { color: 'default', text: '已停止' },
}

export default function InferenceServiceDetailPage() {
  const { id } = useParams<{ id: string }>()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [tokenVisible, setTokenVisible] = useState(() => !!location.state?.authToken)
  const authToken = (location.state as { authToken?: string } | null)?.authToken

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('inference_services:write')

  const { data: svc, isLoading } = useQuery({
    queryKey: ['inferenceService', id],
    queryFn: () => getInferenceService(id!),
    enabled: !!id,
    refetchInterval: (query) => {
      const status = query.state.data?.status
      return status && ['pending', 'deploying'].includes(status) ? 5000 : false
    },
  })

  const regenerateMutation = useMutation({
    mutationFn: () => regenerateToken(id!),
    onSuccess: (token: string) => {
      queryClient.invalidateQueries({ queryKey: ['inferenceService', id] })
      getMessageInstance()?.success('Token 已重新生成')
      Modal.info({
        title: '新的 API Token',
        content: (
          <div>
            <Alert type="warning" message="请妥善保存，仅显示一次" style={{ marginBottom: 12 }} />
            <Typography.Paragraph copyable code style={{ wordBreak: 'break-all' }}>
              {token}
            </Typography.Paragraph>
          </div>
        ),
        width: 560,
      })
    },
  })

  const { data: events = [], isLoading: eventsLoading } = useQuery({
    queryKey: ['inferenceServiceEvents', id],
    queryFn: () => getInferenceServiceEvents(id!),
    enabled: !!id && !!svc?.kserveName && svc.status !== 'pending' && svc.status !== 'stopped',
    refetchInterval: svc?.status === 'running' || svc?.status === 'deploying' ? 30000 : false,
  })

  if (isLoading) return <Spin />
  if (!svc) return null

  const statusCfg = STATUS_CONFIG[svc.status] ?? { color: 'default', text: svc.status }

  const proxyUrl = svc.proxyEndpoint || ''
  const curlExample = proxyUrl
    ? `curl -X POST '${proxyUrl}' \\
  -H 'Authorization: Bearer sk-your-api-token' \\
  -H 'Content-Type: application/json' \\
  -d '{"instances": [[6.8, 2.8, 4.8, 1.4]]}'`
    : ''

  const pythonExample = proxyUrl
    ? `import requests

response = requests.post(
    "${proxyUrl}",
    headers={
        "Authorization": "Bearer sk-your-api-token",
        "Content-Type": "application/json",
    },
    json={"instances": [[6.8, 2.8, 4.8, 1.4]]},
)
print(response.json())`
    : ''

  return (
    <div style={{ padding: 0 }}>
      {tokenVisible && authToken && (
        <Modal
          open={tokenVisible}
          title="API Token"
          onCancel={() => {
            setTokenVisible(false)
            navigate(location.pathname, { replace: true, state: {} })
          }}
          footer={[
            <Button
              key="close"
              type="primary"
              onClick={() => {
                setTokenVisible(false)
                navigate(location.pathname, { replace: true, state: {} })
              }}
            >
              我已保存
            </Button>,
          ]}
          width={560}
        >
          <Alert type="warning" message="请妥善保存，仅显示一次" style={{ marginBottom: 12 }} />
          <Typography.Paragraph copyable code style={{ wordBreak: 'break-all' }}>
            {authToken}
          </Typography.Paragraph>
        </Modal>
      )}

      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between' }}>
        <Typography.Title level={4} style={{ margin: 0 }}>
          推理服务详情 - {svc.name}
        </Typography.Title>
        <Button onClick={() => navigate('/inference')}>返回列表</Button>
      </div>

      <Card
        size="small"
        style={{ marginBottom: 16 }}
        title={
          <Space>
            <span style={{ fontSize: 14 }}>状态:</span>
            {svc.errorMessage && svc.status === 'failed' ? (
              <Tooltip title={svc.errorMessage}>
                <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
              </Tooltip>
            ) : (
              <Tag color={statusCfg.color}>{statusCfg.text}</Tag>
            )}
            {svc.gpuCount > 0 && <span>GPU: {svc.gpuCount} 张</span>}
            <span>副本: {svc.replicas}</span>
          </Space>
        }
      >
        {svc.status === 'failed' && svc.errorMessage && (
          <Alert
            type="error"
            message="推理服务异常"
            description={svc.errorMessage}
            showIcon
            style={{ marginTop: 8 }}
          />
        )}
      </Card>

      <Card size="small" style={{ marginBottom: 16 }} title="端点与认证">
        <Descriptions column={1} size="small">
          <Descriptions.Item label="推理 URL">
            {proxyUrl ? (
              <Space>
                <Typography.Text copyable={{ text: proxyUrl }} style={{ maxWidth: 500 }} ellipsis>
                  {proxyUrl}
                </Typography.Text>
              </Space>
            ) : (
              <Tag>部署后生成</Tag>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="API Token">
            <Space>
              {svc.hasToken ? (
                <>
                  <Tag color="success">已生成</Tag>
                  {canWrite && (
                    <Popconfirm
                      title="重新生成 Token"
                      description="重新生成后旧 Token 将立即失效，确定继续？"
                      onConfirm={() => regenerateMutation.mutate()}
                      okText="确认"
                      cancelText="取消"
                    >
                      <Button
                        size="small"
                        icon={<SyncOutlined />}
                        loading={regenerateMutation.isPending}
                      >
                        重新生成
                      </Button>
                    </Popconfirm>
                  )}
                </>
              ) : (
                <Tag>未生成</Tag>
              )}
            </Space>
          </Descriptions.Item>
        </Descriptions>
        {proxyUrl && (
          <Collapse
            size="small"
            style={{ marginTop: 12 }}
            items={[
              {
                key: 'examples',
                label: '调用示例',
                children: (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <div>
                      <Typography.Text strong>curl</Typography.Text>
                      <Typography.Paragraph
                        copyable
                        code
                        style={{ whiteSpace: 'pre-wrap', marginBottom: 0, marginTop: 4 }}
                      >
                        {curlExample}
                      </Typography.Paragraph>
                    </div>
                    <div>
                      <Typography.Text strong>Python</Typography.Text>
                      <Typography.Paragraph
                        copyable
                        code
                        style={{ whiteSpace: 'pre-wrap', marginBottom: 0, marginTop: 4 }}
                      >
                        {pythonExample}
                      </Typography.Paragraph>
                    </div>
                  </div>
                ),
              },
            ]}
          />
        )}
      </Card>

      <Card size="small" title="基本信息">
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="CPU">{svc.cpu} 核</Descriptions.Item>
          <Descriptions.Item label="内存">{svc.memory}</Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>
            {svc.description || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">{svc.createdAt}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{svc.updatedAt}</Descriptions.Item>
        </Descriptions>
      </Card>

      {svc.kserveName && svc.status !== 'pending' && svc.status !== 'stopped' && (
        <Card size="small" style={{ marginTop: 16 }} title="事件日志">
          {eventsLoading ? (
            <Spin />
          ) : events.length === 0 ? (
            <Typography.Text type="secondary">暂无事件记录</Typography.Text>
          ) : (
            <Table<InferenceServiceEvent>
              dataSource={events}
              rowKey={(record) => `${record.type}-${record.reason}-${record.lastTimestamp}`}
              size="small"
              pagination={false}
              scroll={{ x: 800 }}
              columns={[
                {
                  title: '类型',
                  dataIndex: 'type',
                  width: 80,
                  render: (type: string) => (
                    <Tag color={type === 'Warning' ? 'red' : 'blue'}>
                      {type === 'Warning' ? '警告' : '正常'}
                    </Tag>
                  ),
                },
                {
                  title: '原因',
                  dataIndex: 'reason',
                  width: 120,
                },
                {
                  title: '消息',
                  dataIndex: 'message',
                  ellipsis: { showTitle: false },
                  render: (msg: string) => (
                    <Tooltip title={msg}>
                      <span>{msg}</span>
                    </Tooltip>
                  ),
                },
                {
                  title: '资源',
                  width: 160,
                  render: (_: unknown, record: InferenceServiceEvent) =>
                    `${record.involvedObjectKind}/${record.involvedObjectName}`,
                },
                {
                  title: '时间',
                  dataIndex: 'lastTimestamp',
                  width: 180,
                  render: (ts: string | null) =>
                    ts ? dayjs(ts).format('YYYY-MM-DD HH:mm:ss') : '—',
                },
                {
                  title: '次数',
                  dataIndex: 'count',
                  width: 60,
                },
              ]}
            />
          )}
        </Card>
      )}
    </div>
  )
}
