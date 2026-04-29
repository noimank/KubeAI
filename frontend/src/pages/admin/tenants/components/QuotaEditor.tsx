import { useEffect, useState } from 'react'
import { Button, Form, Input, InputNumber, Modal, Progress, Space, message } from 'antd'
import { getTenantQuotaUsage, updateTenantQuota } from '@/services/tenants'
import type { QuotaUsage, Tenant, TenantQuotaUpdateRequest } from '@/types/tenant'

interface Props {
  tenant: Tenant
  onSuccess: () => void
}

export default function QuotaEditor({ tenant, onSuccess }: Props) {
  const [form] = Form.useForm<TenantQuotaUpdateRequest>()
  const [usage, setUsage] = useState<QuotaUsage | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    form.setFieldsValue({
      gpuLimit: tenant.gpuLimit,
      cpuLimit: tenant.cpuLimit,
      memoryLimit: tenant.memoryLimit,
      storageLimit: tenant.storageLimit,
    })

    getTenantQuotaUsage(tenant.id)
      .then((res) => setUsage(res.data ?? null))
      .catch(() => {})
  }, [tenant, form])

  const handleSubmit = async (values: TenantQuotaUpdateRequest) => {
    setLoading(true)
    try {
      await updateTenantQuota(tenant.id, values)
      message.success('配额更新成功')
      onSuccess()
    } catch (err: unknown) {
      const errResp = err as { response?: { status?: number; data?: { message?: string } } }
      if (errResp.response?.status === 422 && usage) {
        const errMsg = errResp.response.data?.message ?? ''
        if (errMsg.includes('使用量')) {
          Modal.confirm({
            title: '配额调整确认',
            content: errMsg,
            okText: '强制调整',
            cancelText: '取消',
            okButtonProps: { danger: true },
            onOk: async () => {
              try {
                await updateTenantQuota(tenant.id, { ...values, force: true })
                message.success('配额更新成功')
                onSuccess()
              } catch {
                // interceptor handles error toast
              }
            },
          })
          return
        }
      }
      // interceptor handles other error toasts
    } finally {
      setLoading(false)
    }
  }

  const gpuPercent =
    usage && tenant.gpuLimit > 0 ? Math.round((usage.gpuUsed / tenant.gpuLimit) * 100) : 0

  return (
    <Form form={form} layout="vertical" onFinish={handleSubmit}>
      {usage && (
        <div style={{ marginBottom: 16 }}>
          <Space direction="vertical" style={{ width: '100%' }} size="small">
            <div>
              GPU 使用量：{usage.gpuUsed} / {tenant.gpuLimit} 张
              {tenant.gpuLimit > 0 && (
                <Progress percent={gpuPercent} size="small" style={{ marginLeft: 8, width: 120 }} />
              )}
            </div>
          </Space>
        </div>
      )}

      <Form.Item
        name="gpuLimit"
        label="GPU 数量"
        rules={[{ required: true, message: '请输入 GPU 数量' }]}
      >
        <InputNumber min={0} precision={0} style={{ width: '100%' }} placeholder="GPU 数量" />
      </Form.Item>

      <Form.Item
        name="cpuLimit"
        label="CPU 核数"
        rules={[{ required: true, message: '请输入 CPU 核数' }]}
      >
        <Input placeholder='如 "64"' />
      </Form.Item>

      <Form.Item
        name="memoryLimit"
        label="内存"
        rules={[{ required: true, message: '请输入内存限制' }]}
      >
        <Input placeholder='如 "256Gi"' />
      </Form.Item>

      <Form.Item
        name="storageLimit"
        label="存储"
        rules={[{ required: true, message: '请输入存储限制' }]}
      >
        <Input placeholder='如 "500Gi"' />
      </Form.Item>

      <Form.Item>
        <Button type="primary" htmlType="submit" loading={loading}>
          保存
        </Button>
      </Form.Item>
    </Form>
  )
}
