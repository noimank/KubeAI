import { useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import { Button, Form, Input, InputNumber, Modal, Select, message } from 'antd'
import type { DbConnection, DbConnectionCreate, DbConnectionUpdate } from '@/types/dataExplore'
import { DB_DEFAULT_PORTS, DB_TYPE_LABELS } from '@/types/dataExplore'
import type { DbType } from '@/types/dataExplore'
import { testConnection } from '@/services/dataExplore'

const { TextArea } = Input

interface Props {
  open: boolean
  editingConnection: DbConnection | null
  onClose: () => void
  onSuccess: (values: DbConnectionCreate | DbConnectionUpdate, id?: string) => Promise<void>
}

export default function ConnectionFormModal({
  open,
  editingConnection,
  onClose,
  onSuccess,
}: Props) {
  const [form] = Form.useForm()
  const [testing, setTesting] = useState(false)
  const isEdit = !!editingConnection

  useEffect(() => {
    if (open) {
      if (editingConnection) {
        form.setFieldsValue({
          name: editingConnection.name,
          dbType: editingConnection.dbType,
          host: editingConnection.host,
          port: editingConnection.port,
          databaseName: editingConnection.databaseName,
          username: editingConnection.username,
          extraParams: editingConnection.extraParams,
          description: editingConnection.description,
        })
      } else {
        form.resetFields()
      }
    }
  }, [open, editingConnection, form])

  const handleDbTypeChange = (dbType: DbType) => {
    form.setFieldValue('port', DB_DEFAULT_PORTS[dbType])
  }

  const handleTest = async () => {
    // 如果没有保存连接，先通过父组件提交获取 id
    // 仅在编辑模式下可以直接 test
    if (!editingConnection) return
    setTesting(true)
    try {
      const result = await testConnection(editingConnection.id)
      if (result.success) {
        message.success(result.message)
      } else {
        message.error(result.message)
      }
    } catch {
      message.error('测试连接失败')
    } finally {
      setTesting(false)
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      // 编辑模式下移除未填的密码
      if (isEdit && !values.password) {
        delete values.password
      }
      await onSuccess(values, editingConnection?.id)
      onClose()
    } catch {
      // validation failed
    }
  }

  return (
    <Modal
      title={isEdit ? '编辑数据库连接' : '新建数据库连接'}
      open={open}
      onOk={handleSubmit}
      onCancel={onClose}
      width={560}
      destroyOnHidden
      footer={(
        _originNode: ReactNode,
        { OkBtn, CancelBtn }: { OkBtn: React.FC; CancelBtn: React.FC },
      ) => (
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span>
            {isEdit && (
              <Button loading={testing} onClick={handleTest}>
                测试连接
              </Button>
            )}
          </span>
          <span>
            <CancelBtn />
            <OkBtn />
          </span>
        </div>
      )}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item
          name="name"
          label="连接名称"
          rules={[{ required: true, message: '请输入连接名称' }]}
        >
          <Input placeholder="如：生产环境 PG" maxLength={200} />
        </Form.Item>

        <Form.Item
          name="dbType"
          label="数据库类型"
          rules={[{ required: true, message: '请选择数据库类型' }]}
        >
          <Select
            options={Object.entries(DB_TYPE_LABELS).map(([value, label]) => ({ value, label }))}
            onChange={handleDbTypeChange}
          />
        </Form.Item>

        <div style={{ display: 'flex', gap: 12 }}>
          <Form.Item
            name="host"
            label="主机"
            rules={[{ required: true, message: '请输入主机地址' }]}
            style={{ flex: 1 }}
          >
            <Input placeholder="如：192.168.1.100" maxLength={500} />
          </Form.Item>
          <Form.Item
            name="port"
            label="端口"
            rules={[{ required: true, message: '请输入端口' }]}
            style={{ width: 120 }}
          >
            <InputNumber min={1} max={65535} style={{ width: '100%' }} />
          </Form.Item>
        </div>

        <Form.Item
          name="databaseName"
          label="数据库名"
          rules={[{ required: true, message: '请输入数据库名' }]}
        >
          <Input placeholder="如：kubeai" maxLength={200} />
        </Form.Item>

        <div style={{ display: 'flex', gap: 12 }}>
          <Form.Item
            name="username"
            label="用户名"
            rules={[{ required: true, message: '请输入用户名' }]}
            style={{ flex: 1 }}
          >
            <Input placeholder="用户名" maxLength={200} />
          </Form.Item>
          <Form.Item
            name="password"
            label="密码"
            rules={isEdit ? [] : [{ required: true, message: '请输入密码' }]}
            style={{ flex: 1 }}
          >
            <Input.Password placeholder={isEdit ? '留空则不修改' : '输入密码'} />
          </Form.Item>
        </div>

        <Form.Item name="extraParams" label="额外参数 (JSON)">
          <TextArea rows={3} placeholder='如：{"charset": "utf8mb4"}' />
        </Form.Item>

        <Form.Item name="description" label="备注">
          <Input placeholder="备注信息" maxLength={500} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
