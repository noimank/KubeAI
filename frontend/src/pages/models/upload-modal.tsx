import { useMemo, useState } from 'react'
import { Button, Input, Modal, Tabs, Typography, Upload } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import type { UploadChangeParam, UploadFile } from 'antd/es/upload/interface'
import { getMessageInstance } from '@/utils/messageHolder'
import { uploadModelFiles, registerModel } from '@/services/models'
import type { ModelVersion } from '@/types/model'
import { useAuthStore } from '@/stores/authStore'
import { useTenantStore } from '@/stores/tenantStore'
import FileBrowser from '@/components/FileBrowser'

type UploadTab = 'local' | 'browser'

interface UploadModalProps {
  open: boolean
  onClose: () => void
  onSuccess: (version: ModelVersion) => void
  /** 若提供，则为"上传新版本"模式，名称锁定 */
  modelId?: string
  modelName?: string
}

export default function UploadModal({
  open,
  onClose,
  onSuccess,
  modelId,
  modelName = '',
}: UploadModalProps) {
  const [tab, setTab] = useState<UploadTab>('local')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])

  const authUser = useAuthStore((s) => s.user)
  const currentTenant = useTenantStore((s) => s.currentTenant)
  const browserRoots = useMemo<string[]>(
    () => (authUser && currentTenant ? ['/kubeai/home', '/kubeai/workspace'] : []),
    [authUser, currentTenant],
  )

  const isVersionMode = Boolean(modelId)

  const uploadMutation = useMutation({
    mutationFn: uploadModelFiles,
    onSuccess: (version) => {
      getMessageInstance()?.success(isVersionMode ? '新版本上传成功' : '模型上传成功')
      onSuccess(version)
      resetForm()
    },
  })

  const registerMutation = useMutation({
    mutationFn: registerModel,
    onSuccess: (version) => {
      getMessageInstance()?.success(isVersionMode ? '新版本注册成功' : '模型注册成功')
      onSuccess(version)
      resetForm()
    },
  })

  const isSubmitting = uploadMutation.isPending || registerMutation.isPending

  const resetForm = () => {
    setName('')
    setDescription('')
    setFileList([])
    setSelectedPaths([])
    setTab('local')
  }

  const handleUploadChange = (info: UploadChangeParam) => {
    setFileList(info.fileList)
  }

  const handleOk = () => {
    if (tab === 'local') {
      if (!isVersionMode && !name.trim()) {
        getMessageInstance()?.warning('请输入模型名称')
        return
      }
      if (fileList.length === 0) {
        getMessageInstance()?.warning('请选择模型文件')
        return
      }
      const files = fileList.filter((f) => f.originFileObj).map((f) => f.originFileObj as File)
      uploadMutation.mutate({
        name: isVersionMode ? undefined : name.trim(),
        modelId: modelId || undefined,
        description: description.trim() || undefined,
        files,
      })
    } else {
      if (!isVersionMode && !name.trim()) {
        getMessageInstance()?.warning('请输入模型名称')
        return
      }
      if (selectedPaths.length === 0) {
        getMessageInstance()?.warning('请至少勾选一个文件或目录')
        return
      }
      registerMutation.mutate({
        name: isVersionMode ? modelName || name.trim() : name.trim(),
        description: description.trim() || undefined,
        filePaths: selectedPaths,
      })
    }
  }

  const handleCancel = () => {
    onClose()
    resetForm()
  }

  const nameField = (
    <div>
      <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>模型名称 *</label>
      <Input
        placeholder="输入模型名称（同名模型将追加版本）"
        value={name}
        onChange={(e) => setName(e.target.value)}
        maxLength={200}
      />
    </div>
  )

  const descField = (
    <div>
      <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>描述</label>
      <Input.TextArea
        placeholder="版本描述（可选）"
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        rows={3}
      />
    </div>
  )

  const localTab = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 8 }}>
      {isVersionMode ? (
        <div style={{ padding: '8px 0', color: '#666' }}>
          将为模型 <strong>{modelName}</strong> 创建新版本，版本号自动递增
        </div>
      ) : (
        nameField
      )}
      {descField}
      <div>
        <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>模型文件 *</label>
        <Upload
          multiple
          beforeUpload={() => false}
          fileList={fileList}
          onChange={handleUploadChange}
        >
          <Button icon={<UploadOutlined />}>选择文件</Button>
        </Upload>
      </div>
    </div>
  )

  const browserTab = (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
      {isVersionMode ? (
        <div style={{ padding: '8px 0', color: '#666' }}>
          将为模型 <strong>{modelName}</strong> 创建新版本，版本号自动递增
        </div>
      ) : (
        <div>
          <Typography.Text strong>模型名称 *</Typography.Text>
          <Input
            placeholder="输入模型名称（同名模型将追加版本）"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={200}
            style={{ marginTop: 4 }}
          />
        </div>
      )}
      <div>
        <Typography.Text strong>描述</Typography.Text>
        <Input.TextArea
          placeholder="版本描述（可选）"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={2}
          style={{ marginTop: 4 }}
        />
      </div>
      <div>
        <Typography.Text strong>选择模型文件或目录 *</Typography.Text>
        <div style={{ marginTop: 4 }}>
          <FileBrowser value={selectedPaths} onChange={setSelectedPaths} roots={browserRoots} />
        </div>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          仅允许浏览个人目录 <code>/kubeai/home</code> 与当前租户工作空间{' '}
          <code>/kubeai/workspace</code>; 注册时目录会按子树整体打包为 zip。
        </Typography.Text>
      </div>
    </div>
  )

  return (
    <Modal
      title={isVersionMode ? `上传新版本 - ${modelName}` : '上传模型'}
      open={open}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={isSubmitting}
      okText="上传"
      cancelText="取消"
      width={680}
      destroyOnHidden
    >
      <Tabs
        activeKey={tab}
        onChange={(key) => setTab(key as UploadTab)}
        items={[
          { key: 'local', label: '本地上传', children: localTab },
          { key: 'browser', label: '从文件浏览器选择', children: browserTab },
        ]}
      />
    </Modal>
  )
}
