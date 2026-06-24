import { useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import {
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Input,
  Modal,
  Popconfirm,
  Space,
  Spin,
  Tag,
} from 'antd'
import { DownloadOutlined, EditOutlined, DeleteOutlined, CodeOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useRbacStore } from '@/stores/rbacStore'
import { getMessageInstance } from '@/utils/messageHolder'
import { formatDate, formatFileSize } from '@/utils/format'
import {
  getAlgorithm,
  updateAlgorithm,
  deleteAlgorithm,
  downloadAlgorithm,
} from '@/services/algorithms'

export default function AlgorithmDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canManage = hasPermission('algorithms:manage')

  const [editModalOpen, setEditModalOpen] = useState(false)
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [editTags, setEditTags] = useState('')

  const {
    data: algo,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['algorithm-detail', id],
    queryFn: () => getAlgorithm(id!),
    enabled: !!id,
  })

  const updateMutation = useMutation({
    mutationFn: (params: { name?: string; description?: string; tags?: string[] }) =>
      updateAlgorithm(id!, params),
    onSuccess: () => {
      getMessageInstance()?.success('算法更新成功')
      setEditModalOpen(false)
      queryClient.invalidateQueries({ queryKey: ['algorithm-detail', id] })
      queryClient.invalidateQueries({ queryKey: ['algorithms'] })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteAlgorithm(id!),
    onSuccess: () => {
      getMessageInstance()?.success('算法删除成功')
      navigate('/algorithms', { replace: true })
    },
  })

  const handleEditOpen = () => {
    if (!algo) return
    setEditName(algo.name)
    setEditDesc(algo.description || '')
    setEditTags(algo.tags?.join(', ') || '')
    setEditModalOpen(true)
  }

  const handleEditOk = () => {
    if (!editName.trim()) return
    const tags = editTags
      .split(',')
      .map((t) => t.trim())
      .filter(Boolean)
    updateMutation.mutate({
      name: editName.trim(),
      description: editDesc.trim() || undefined,
      tags: tags.length > 0 ? tags : undefined,
    })
  }

  const handleDownload = async () => {
    if (!algo) return
    try {
      await downloadAlgorithm(id!, `${algo.name}.zip`)
    } catch {
      getMessageInstance()?.error('下载失败，请稍后重试')
    }
  }

  if (isLoading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 300 }}>
        <Spin spinning />
      </div>
    )
  }

  if (error || !algo) {
    return (
      <div style={{ textAlign: 'center', padding: 60 }}>
        <p style={{ color: '#999', marginBottom: 16 }}>{error ? '加载失败' : '算法不存在'}</p>
        <Link to="/algorithms">返回算法列表</Link>
      </div>
    )
  }

  return (
    <div>
      <Breadcrumb
        style={{ marginBottom: 16 }}
        items={[{ title: <Link to="/algorithms">算法管理</Link> }, { title: algo.name }]}
      />

      <Card>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <h2 style={{ margin: 0 }}>{algo.name}</h2>
          <Space>
            <Button
              icon={<CodeOutlined />}
              onClick={() => navigate(`/dev-environments/create?algorithmId=${algo.id}`)}
            >
              创建开发环境
            </Button>
            <Button icon={<DownloadOutlined />} onClick={handleDownload}>
              下载
            </Button>
            {canManage && (
              <>
                <Button icon={<EditOutlined />} onClick={handleEditOpen}>
                  编辑
                </Button>
                <Popconfirm
                  title="确认删除该算法？"
                  description="删除后不可恢复。"
                  onConfirm={() => deleteMutation.mutate()}
                  okText="确认"
                  cancelText="取消"
                >
                  <Button danger icon={<DeleteOutlined />} loading={deleteMutation.isPending}>
                    删除
                  </Button>
                </Popconfirm>
              </>
            )}
          </Space>
        </div>

        <Descriptions bordered column={2} style={{ marginTop: 24 }}>
          <Descriptions.Item label="名称">{algo.name}</Descriptions.Item>
          <Descriptions.Item label="文件大小">
            {algo.sizeBytes ? formatFileSize(algo.sizeBytes) : '—'}
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>
            {algo.description || '—'}
          </Descriptions.Item>
          <Descriptions.Item label="标签" span={2}>
            {algo.tags && algo.tags.length > 0 ? (
              <Space size={4} wrap>
                {algo.tags.map((t) => (
                  <Tag key={t} color="blue">
                    {t}
                  </Tag>
                ))}
              </Space>
            ) : (
              '—'
            )}
          </Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={algo.status === 'available' ? 'green' : 'default'}>
              {algo.status === 'available' ? '可用' : algo.status}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="上传者">{algo.uploader?.username || '—'}</Descriptions.Item>
          <Descriptions.Item label="创建时间">{formatDate(algo.createdAt)}</Descriptions.Item>
          <Descriptions.Item label="更新时间">{formatDate(algo.updatedAt)}</Descriptions.Item>
          <Descriptions.Item label="可见性">
            <Tag>{algo.visibility === 'tenant' ? '租户内共享' : algo.visibility}</Tag>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Modal
        title="编辑算法"
        open={editModalOpen}
        onOk={handleEditOk}
        onCancel={() => setEditModalOpen(false)}
        confirmLoading={updateMutation.isPending}
        okText="保存"
        cancelText="取消"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 8 }}>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>名称</label>
            <Input value={editName} onChange={(e) => setEditName(e.target.value)} maxLength={200} />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>描述</label>
            <Input.TextArea
              value={editDesc}
              onChange={(e) => setEditDesc(e.target.value)}
              rows={3}
            />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
              标签（逗号分隔）
            </label>
            <Input
              value={editTags}
              onChange={(e) => setEditTags(e.target.value)}
              placeholder="如: 图像分割, 优化算法"
            />
          </div>
        </div>
      </Modal>
    </div>
  )
}
