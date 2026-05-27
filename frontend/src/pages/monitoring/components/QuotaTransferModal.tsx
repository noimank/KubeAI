import { useEffect, useState } from 'react'
import {
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Radio,
  Row,
  Select,
  Space,
  Typography,
} from 'antd'
import { getMessageInstance } from '@/utils/messageHolder'
import { getModalInstance } from '@/utils/modalHolder'
import { transferQuota } from '@/services/monitoring'
import type { QuotaTransferRequest, TenantQuotaComparison } from '@/types/monitoring'
import { formatKi } from '@/utils/format'

interface Props {
  open: boolean
  tenants: TenantQuotaComparison[]
  preselectedTenant?: TenantQuotaComparison
  onClose: () => void
  onSuccess: () => void
}

function formatQuotaValue(type: string, val: number): string {
  if (type === 'memory' || type === 'storage') return formatKi(val)
  return `${val}`
}

function TenantCard({
  title,
  tenant,
  resourceType,
  delta,
}: {
  title: string
  tenant: TenantQuotaComparison | undefined
  resourceType: string
  delta: number
}) {
  if (!tenant) return null
  const item = tenant[resourceType as keyof TenantQuotaComparison] as {
    quota: number
    used: number
    utilization: number
  }
  const newQuota = item.quota + delta

  return (
    <Card size="small" title={title} style={{ marginBottom: 8 }}>
      <Space direction="vertical" size={4}>
        <Typography.Text style={{ fontSize: 12 }}>
          当前配额: {formatQuotaValue(resourceType, item.quota)}
        </Typography.Text>
        <Typography.Text style={{ fontSize: 12 }}>
          已使用: {formatQuotaValue(resourceType, item.used)} ({item.utilization.toFixed(1)}%)
        </Typography.Text>
        <Typography.Text style={{ fontSize: 12, color: delta < 0 ? '#ff4d4f' : '#52c41a' }}>
          调配后: {formatQuotaValue(resourceType, newQuota)}
        </Typography.Text>
      </Space>
    </Card>
  )
}

export default function QuotaTransferModal({
  open,
  tenants,
  preselectedTenant,
  onClose,
  onSuccess,
}: Props) {
  const [form] = Form.useForm()
  const [loading, setLoading] = useState(false)
  const [sourceId, setSourceId] = useState<string | undefined>()
  const [targetId, setTargetId] = useState<string | undefined>()
  const [resourceType, setResourceType] = useState<string>('gpu')
  const [amount, setAmount] = useState<string>('0')

  useEffect(() => {
    if (open) {
      const initValues: Record<string, unknown> = { resourceType: 'gpu', amount: undefined }
      if (preselectedTenant) {
        setSourceId(preselectedTenant.tenantId)
        initValues.sourceTenantId = preselectedTenant.tenantId
      } else {
        setSourceId(undefined)
        initValues.sourceTenantId = undefined
      }
      setTargetId(undefined)
      setResourceType('gpu')
      setAmount('0')
      form.resetFields()
      form.setFieldsValue(initValues)
    }
  }, [open, preselectedTenant, form])

  const source = tenants.find((t) => t.tenantId === sourceId)
  const target = tenants.find((t) => t.tenantId === targetId)

  const parsedAmount = (() => {
    if (!amount) return 0
    return resourceType === 'gpu' ? parseInt(amount, 10) || 0 : parseFloat(amount) || 0
  })()

  const sourceDelta = -(parsedAmount || 0)
  const targetDelta = parsedAmount || 0

  const handleSubmit = async (values: {
    sourceTenantId: string
    targetTenantId: string
    resourceType: string
    amount: string
  }) => {
    setLoading(true)
    try {
      const req: QuotaTransferRequest = {
        sourceTenantId: values.sourceTenantId,
        targetTenantId: values.targetTenantId,
        resourceType: values.resourceType as QuotaTransferRequest['resourceType'],
        amount: values.amount,
      }
      await transferQuota(req)
      getMessageInstance()?.success('配额调配成功')
      onSuccess()
      onClose()
    } catch (err: unknown) {
      const errResp = err as { response?: { status?: number; data?: { message?: string } } }
      if (errResp.response?.status === 422) {
        const errMsg = errResp.response.data?.message ?? '调配失败'
        getModalInstance()?.confirm({
          title: '配额调配确认',
          content: errMsg,
          okText: '强制调配',
          cancelText: '取消',
          okButtonProps: { danger: true },
          onOk: async () => {
            try {
              const req: QuotaTransferRequest = {
                sourceTenantId: values.sourceTenantId,
                targetTenantId: values.targetTenantId,
                resourceType: values.resourceType as QuotaTransferRequest['resourceType'],
                amount: values.amount,
                force: true,
              }
              await transferQuota(req)
              getMessageInstance()?.success('配额调配成功')
              onSuccess()
              onClose()
            } catch {
              // interceptor handles error toast
            }
          },
        })
        return
      }
      // interceptor handles other errors
    } finally {
      setLoading(false)
    }
  }

  const tenantOptions = tenants.map((t) => ({
    label: `${t.tenantName} (GPU: ${t.gpu.quota}张)`,
    value: t.tenantId,
  }))

  return (
    <Modal
      title="配额调配"
      open={open}
      onCancel={onClose}
      onOk={() => form.submit()}
      confirmLoading={loading}
      width={720}
      destroyOnHidden
    >
      <Row gutter={16}>
        <Col span={14}>
          <Form form={form} layout="vertical" onFinish={handleSubmit}>
            <Form.Item
              name="sourceTenantId"
              label="源租户（调出方）"
              rules={[{ required: true, message: '请选择源租户' }]}
            >
              <Select
                placeholder="选择源租户"
                options={tenantOptions}
                onChange={(v) => setSourceId(v)}
              />
            </Form.Item>

            <Form.Item
              name="targetTenantId"
              label="目标租户（调入方）"
              rules={[{ required: true, message: '请选择目标租户' }]}
            >
              <Select
                placeholder="选择目标租户"
                options={tenantOptions.filter((o) => o.value !== sourceId)}
                onChange={(v) => setTargetId(v)}
              />
            </Form.Item>

            <Form.Item name="resourceType" label="资源类型" rules={[{ required: true }]}>
              <Radio.Group
                onChange={(e) => {
                  setResourceType(e.target.value)
                  setAmount('0')
                  form.setFieldValue('amount', undefined)
                }}
              >
                <Radio value="gpu">GPU</Radio>
                <Radio value="cpu">CPU</Radio>
                <Radio value="memory">内存</Radio>
                <Radio value="storage">存储</Radio>
              </Radio.Group>
            </Form.Item>

            <Form.Item
              name="amount"
              label="调配量"
              rules={[{ required: true, message: '请输入调配量' }]}
            >
              {resourceType === 'gpu' ? (
                <InputNumber
                  min={1}
                  precision={0}
                  style={{ width: '100%' }}
                  placeholder="GPU 数量"
                  onChange={(v) => setAmount(String(v ?? 0))}
                />
              ) : (
                <Input
                  placeholder={resourceType === 'cpu' ? '如 "4"' : '如 "16Gi"'}
                  onChange={(e) => setAmount(e.target.value)}
                />
              )}
            </Form.Item>
          </Form>
        </Col>
        <Col span={10}>
          <Typography.Text strong style={{ display: 'block', marginBottom: 8 }}>
            调配预览
          </Typography.Text>
          <TenantCard
            title="源租户"
            tenant={source}
            resourceType={resourceType}
            delta={sourceDelta}
          />
          <TenantCard
            title="目标租户"
            tenant={target}
            resourceType={resourceType}
            delta={targetDelta}
          />
        </Col>
      </Row>
    </Modal>
  )
}
