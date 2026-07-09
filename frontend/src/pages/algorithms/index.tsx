import { useMemo, useState, useCallback } from 'react'
import { Button, Input, Modal, Popconfirm, Space, Table, Tabs, Tag, Typography, Upload } from 'antd'
import { Link, useNavigate } from 'react-router-dom'
import { PlusOutlined, SearchOutlined, UploadOutlined } from '@ant-design/icons'
import type { ColumnsType, TablePaginationConfig } from 'antd/es/table'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getMessageInstance } from '@/utils/messageHolder'
import { useRbacStore } from '@/stores/rbacStore'
import { useAuthStore } from '@/stores/authStore'
import { useTenantStore } from '@/stores/tenantStore'
import FileBrowser from '@/components/FileBrowser'
import {
  createAlgorithm,
  deleteAlgorithm,
  getAlgorithms,
  registerAlgorithm,
} from '@/services/algorithms'
import { formatDate, formatFileSize } from '@/utils/format'
import type { Algorithm } from '@/types/algorithm'
import type { RcFile, UploadChangeParam } from 'antd/es/upload/interface'

type UploadTab = 'local' | 'browser'

export default function AlgorithmsPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState<string>()
  const [searchText, setSearchText] = useState('')

  const [uploadModalOpen, setUploadModalOpen] = useState(false)
  const [uploadTab, setUploadTab] = useState<UploadTab>('local')
  const [newName, setNewName] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newTags, setNewTags] = useState('')
  const [selectedFile, setSelectedFile] = useState<RcFile | null>(null)
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])

  const hasPermission = useRbacStore((s) => s.hasPermission)
  const canWrite = hasPermission('algorithms:write')
  const canManage = hasPermission('algorithms:manage')

  const authUser = useAuthStore((s) => s.user)
  const currentTenant = useTenantStore((s) => s.currentTenant)
  const browserRoots = useMemo<string[]>(() => {
    if (!authUser || !currentTenant) return []
    return [`/kubeai/home/${authUser.username}`, `/kubeai/workspace/${currentTenant.name}`]
  }, [authUser, currentTenant])

  const { data, isLoading } = useQuery({
    queryKey: ['algorithms', page, pageSize, keyword],
    queryFn: () =>
      getAlgorithms({
        current: page,
        pageSize,
        name: keyword,
      }),
  })

  const resetUpload = () => {
    setNewName('')
    setNewDesc('')
    setNewTags('')
    setSelectedFile(null)
    setSelectedPaths([])
    setUploadTab('local')
  }

  const handleSuccess = useCallback(
    (detail: { id: string }, msg: string) => {
      getMessageInstance()?.success(msg)
      setUploadModalOpen(false)
      resetUpload()
      queryClient.invalidateQueries({ queryKey: ['algorithms'] })
      navigate(`/algorithms/${detail.id}`)
    },
    [queryClient, navigate],
  )

  const uploadMutation = useMutation({
    mutationFn: createAlgorithm,
    onSuccess: (detail) => handleSuccess(detail, '算法上传成功'),
  })

  const registerMutation = useMutation({
    mutationFn: registerAlgorithm,
    onSuccess: (detail) => handleSuccess(detail, '算法注册成功'),
  })

  const isSubmitting = uploadMutation.isPending || registerMutation.isPending

  const handleSearch = useCallback((value: string) => {
    setKeyword(value || undefined)
    setPage(1)
  }, [])

  const handleTableChange = useCallback((pagination: TablePaginationConfig) => {
    setPage(pagination.current || 1)
    setPageSize(pagination.pageSize || 20)
  }, [])

  const handleDelete = async (id: string) => {
    try {
      await deleteAlgorithm(id)
      getMessageInstance()?.success('算法删除成功')
      queryClient.invalidateQueries({ queryKey: ['algorithms'] })
    } catch {
      // interceptor handles error toast
    }
  }

  const handleFileSelect = (info: UploadChangeParam) => {
    const file = info.file as RcFile
    if (file) setSelectedFile(file)
  }

  const handleUploadOk = () => {
    if (!newName.trim()) {
      getMessageInstance()?.warning('请输入算法名称')
      return
    }
    if (uploadTab === 'local') {
      if (!selectedFile) {
        getMessageInstance()?.warning('请选择算法文件')
        return
      }
      uploadMutation.mutate({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        tags: newTags.trim() || undefined,
        file: selectedFile,
      })
    } else {
      if (selectedPaths.length === 0) {
        getMessageInstance()?.warning('请至少勾选一个文件或目录')
        return
      }
      const tagList = newTags
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
      registerMutation.mutate({
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        tags: tagList.length > 0 ? tagList : undefined,
        filePaths: selectedPaths,
      })
    }
  }

  const columns: ColumnsType<Algorithm> = [
    {
      title: '名称',
      dataIndex: 'name',
      ellipsis: true,
      render: (name: string, record: Algorithm) => (
        <Link to={`/algorithms/${record.id}`} style={{ fontWeight: 500 }}>
          {name}
        </Link>
      ),
    },
    {
      title: '标签',
      dataIndex: 'tags',
      width: 200,
      render: (tags: string[]) =>
        tags && tags.length > 0 ? (
          <Space size={4} wrap>
            {tags.slice(0, 4).map((t) => (
              <Tag key={t} color="blue">
                {t}
              </Tag>
            ))}
            {tags.length > 4 && <Tag>+{tags.length - 4}</Tag>}
          </Space>
        ) : (
          <span style={{ color: '#bbb' }}>—</span>
        ),
    },
    {
      title: '大小',
      dataIndex: 'sizeBytes',
      width: 100,
      render: (_, record) => (record.sizeBytes ? formatFileSize(record.sizeBytes) : '—'),
    },
    {
      title: '上传者',
      dataIndex: 'uploader',
      width: 120,
      render: (uploader: Algorithm['uploader']) => uploader?.username || '—',
    },
    {
      title: '创建时间',
      dataIndex: 'createdAt',
      width: 170,
      render: (v: string) => formatDate(v),
    },
    {
      title: '操作',
      width: 140,
      render: (_, record) => (
        <Space size="small">
          <Link to={`/algorithms/${record.id}`}>
            <Button type="link" size="small">
              详情
            </Button>
          </Link>
          {canManage && (
            <Popconfirm
              title="确认删除该算法？"
              description="删除后，算法文件将被永久清除。"
              onConfirm={() => handleDelete(record.id)}
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

  return (
    <div style={{ padding: 0 }}>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
        <Input.Search
          placeholder="搜索算法名称"
          allowClear
          style={{ width: 280 }}
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onSearch={handleSearch}
          prefix={<SearchOutlined />}
        />
        {canWrite && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setUploadModalOpen(true)}>
            上传算法
          </Button>
        )}
      </div>

      <Table<Algorithm>
        rowKey="id"
        columns={columns}
        dataSource={data?.items}
        loading={isLoading}
        onChange={handleTableChange}
        pagination={{
          current: page,
          pageSize,
          total: data?.total,
          showSizeChanger: true,
          pageSizeOptions: ['20', '50', '100'],
          showTotal: (total) => `共 ${total} 个算法`,
        }}
      />

      {/* Upload Modal */}
      <Modal
        title="上传算法"
        open={uploadModalOpen}
        onOk={handleUploadOk}
        onCancel={() => {
          setUploadModalOpen(false)
          resetUpload()
        }}
        confirmLoading={isSubmitting}
        okText="上传"
        cancelText="取消"
        width={680}
      >
        <Tabs
          activeKey={uploadTab}
          onChange={(key) => setUploadTab(key as UploadTab)}
          items={[
            {
              key: 'local',
              label: '本地上传',
              children: (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 8 }}>
                  <div>
                    <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                      算法名称 *
                    </label>
                    <Input
                      placeholder="输入算法名称"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      maxLength={200}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                      描述
                    </label>
                    <Input.TextArea
                      placeholder="算法描述（可选）"
                      value={newDesc}
                      onChange={(e) => setNewDesc(e.target.value)}
                      rows={3}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                      标签（逗号分隔）
                    </label>
                    <Input
                      placeholder="如: 图像分割, 优化算法"
                      value={newTags}
                      onChange={(e) => setNewTags(e.target.value)}
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>
                      算法文件 *
                    </label>
                    <Upload
                      maxCount={1}
                      beforeUpload={() => false}
                      onChange={handleFileSelect}
                      onRemove={() => setSelectedFile(null)}
                    >
                      <Button icon={<UploadOutlined />}>选择文件（目录请先打包为 zip）</Button>
                    </Upload>
                  </div>
                </div>
              ),
            },
            {
              key: 'browser',
              label: '从文件浏览器选择',
              children: (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
                  <div>
                    <Typography.Text strong>算法名称 *</Typography.Text>
                    <Input
                      placeholder="输入算法名称"
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      maxLength={200}
                      style={{ marginTop: 4 }}
                    />
                  </div>
                  <div>
                    <Typography.Text strong>描述</Typography.Text>
                    <Input.TextArea
                      placeholder="算法描述（可选）"
                      value={newDesc}
                      onChange={(e) => setNewDesc(e.target.value)}
                      rows={2}
                      style={{ marginTop: 4 }}
                    />
                  </div>
                  <div>
                    <Typography.Text strong>标签（逗号分隔）</Typography.Text>
                    <Input
                      placeholder="如: 图像分割, 优化算法"
                      value={newTags}
                      onChange={(e) => setNewTags(e.target.value)}
                      style={{ marginTop: 4 }}
                    />
                  </div>
                  <div>
                    <Typography.Text strong>选择算法文件或目录 *</Typography.Text>
                    <div style={{ marginTop: 4 }}>
                      <FileBrowser
                        value={selectedPaths}
                        onChange={setSelectedPaths}
                        roots={browserRoots}
                      />
                    </div>
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      仅允许浏览个人目录 <code>/kubeai/home/&lt;自己&gt;</code> 与当前租户工作空间{' '}
                      <code>/kubeai/workspace/&lt;当前租户&gt;</code>; 注册时目录会按子树整体打包为
                      zip。
                    </Typography.Text>
                  </div>
                </div>
              ),
            },
          ]}
        />
      </Modal>
    </div>
  )
}
