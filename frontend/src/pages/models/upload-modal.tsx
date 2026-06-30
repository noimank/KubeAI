import { useState } from 'react'
import { Button, Input, Modal, Upload } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { useMutation } from '@tanstack/react-query'
import type { UploadChangeParam, UploadFile } from 'antd/es/upload/interface'
import { getMessageInstance } from '@/utils/messageHolder'
import { uploadModelFiles } from '@/services/models'
import type { ModelVersion } from '@/types/model'

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
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [fileList, setFileList] = useState<UploadFile[]>([])

  const isVersionMode = Boolean(modelId)

  const uploadMutation = useMutation({
    mutationFn: uploadModelFiles,
    onSuccess: (version) => {
      getMessageInstance()?.success(isVersionMode ? '新版本上传成功' : '模型上传成功')
      onSuccess(version)
      resetForm()
    },
  })

  const resetForm = () => {
    setName('')
    setDescription('')
    setFileList([])
  }

  const handleOk = () => {
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
  }

  const handleCancel = () => {
    onClose()
    resetForm()
  }

  const handleUploadChange = (info: UploadChangeParam) => {
    setFileList(info.fileList)
  }

  return (
    <Modal
      title={isVersionMode ? `上传新版本 - ${modelName}` : '本地上传模型'}
      open={open}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={uploadMutation.isPending}
      okText="上传"
      cancelText="取消"
      destroyOnHidden
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginTop: 8 }}>
        {isVersionMode ? (
          <div style={{ padding: '8px 0', color: '#666' }}>
            将为模型 <strong>{modelName}</strong> 创建新版本，版本号自动递增
          </div>
        ) : (
          <div>
            <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>模型名称 *</label>
            <Input
              placeholder="输入模型名称（同名模型将追加版本）"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={200}
            />
          </div>
        )}
        <div>
          <label style={{ display: 'block', marginBottom: 4, fontWeight: 500 }}>描述</label>
          <Input.TextArea
            placeholder="版本描述（可选）"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
          />
        </div>
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
    </Modal>
  )
}
