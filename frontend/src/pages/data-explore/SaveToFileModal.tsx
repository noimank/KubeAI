import { useState, useMemo, useCallback } from 'react'
import { Form, Input, Modal } from 'antd'
import dayjs from 'dayjs'
import FileBrowser from '@/components/FileBrowser'
import { useAuthStore } from '@/stores/authStore'
import { useTenantStore } from '@/stores/tenantStore'

interface Props {
  open: boolean
  onClose: () => void
  onSave: (targetPath: string, filename: string) => Promise<void>
}

export default function SaveToFileModal({ open, onClose, onSave }: Props) {
  const [form] = Form.useForm()
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const authUser = useAuthStore((s) => s.user)
  const currentTenant = useTenantStore((s) => s.currentTenant)

  const browserRoots = useMemo(() => {
    if (authUser && currentTenant) return ['/kubeai/home', '/kubeai/workspace']
    return []
  }, [authUser, currentTenant])

  const handlePathChange = useCallback(
    (paths: string[]) => setSelectedPaths(paths.length > 1 ? [paths[paths.length - 1]] : paths),
    [],
  )

  const handleSave = async () => {
    const values = await form.validateFields()
    const targetPath = selectedPaths[0]
    if (!targetPath) return
    setSaving(true)
    try {
      await onSave(targetPath, values.filename)
      form.resetFields()
      setSelectedPaths([])
      onClose()
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      title="保存查询结果到平台"
      open={open}
      onOk={handleSave}
      onCancel={() => {
        form.resetFields()
        setSelectedPaths([])
        onClose()
      }}
      confirmLoading={saving}
      okText="保存"
      cancelText="取消"
      width={600}
      destroyOnHidden
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{
          filename: `query_result_${dayjs().format('YYYYMMDD_HHmmss')}.csv`,
        }}
        style={{ marginTop: 16 }}
      >
        <Form.Item label="选择目标目录" required>
          <FileBrowser
            roots={browserRoots}
            value={selectedPaths}
            onChange={handlePathChange}
            height={300}
          />
          {selectedPaths.length > 0 && (
            <div style={{ marginTop: 8, color: '#666', fontSize: 12 }}>
              目标目录：{selectedPaths[0]}
            </div>
          )}
        </Form.Item>

        <Form.Item
          name="filename"
          label="文件名"
          rules={[{ required: true, message: '请输入文件名' }]}
        >
          <Input placeholder="如：result.csv" />
        </Form.Item>
      </Form>
    </Modal>
  )
}
