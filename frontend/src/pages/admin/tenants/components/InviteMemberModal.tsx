import { useState } from 'react'
import { Button, Form, Input, Select } from 'antd'
import { CopyOutlined } from '@ant-design/icons'
import { getMessageInstance } from '@/utils/messageHolder'
import { copyToClipboard } from '@/utils/clipboard'
import { createInvitation } from '@/services/tenants'
import { ROLE_OPTIONS } from '@/utils/roleLabels'

interface Props {
  tenantId: string
  onSuccess?: () => void
}

export default function InviteMemberModal({ tenantId, onSuccess }: Props) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [inviteLink, setInviteLink] = useState<string | null>(null)

  const handleSubmit = async (values: { email: string; role: string }) => {
    setLoading(true)
    try {
      const res = await createInvitation(tenantId, values)
      if (res.success && res.data) {
        const baseUrl = window.location.origin
        const link = `${baseUrl}/invite?token=${res.data.token}`
        setInviteLink(link)
        getMessageInstance()?.success('邀请创建成功')
        onSuccess?.()
      }
    } catch {
      // interceptor handles error toast
    } finally {
      setLoading(false)
    }
  }

  const handleCopy = async () => {
    if (inviteLink) {
      const ok = await copyToClipboard(inviteLink)
      if (ok) getMessageInstance()?.success('邀请链接已复制')
      else getMessageInstance()?.error('复制失败，请手动复制')
    }
  }

  const handleReset = () => {
    form.resetFields()
    setInviteLink(null)
  }

  if (inviteLink) {
    return (
      <div style={{ padding: '8px 0' }}>
        <p style={{ marginBottom: 12 }}>邀请链接已生成，请复制后发送给被邀请人：</p>
        <Input.Group compact>
          <Input value={inviteLink} readOnly style={{ width: 'calc(100% - 80px)' }} />
          <Button icon={<CopyOutlined />} onClick={handleCopy}>
            复制
          </Button>
        </Input.Group>
        <div style={{ marginTop: 16, textAlign: 'right' }}>
          <Button onClick={handleReset}>继续邀请</Button>
        </div>
      </div>
    )
  }

  return (
    <Form form={form} layout="vertical" onFinish={handleSubmit} style={{ padding: '8px 0' }}>
      <Form.Item
        name="email"
        label="邮箱地址"
        rules={[{ required: true, type: 'email', message: '请输入有效的邮箱地址' }]}
      >
        <Input placeholder="请输入被邀请人邮箱" />
      </Form.Item>
      <Form.Item
        name="role"
        label="角色"
        rules={[{ required: true, message: '请选择角色' }]}
        initialValue="engineer"
      >
        <Select options={ROLE_OPTIONS} placeholder="请选择角色" />
      </Form.Item>
      <Form.Item style={{ marginBottom: 0, textAlign: 'right' }}>
        <Button type="primary" htmlType="submit" loading={loading}>
          创建邀请
        </Button>
      </Form.Item>
    </Form>
  )
}
