import { ProFormText, ProFormTextArea } from '@ant-design/pro-components'
import { ProForm } from '@ant-design/pro-components'
import type { Tenant } from '@/types/tenant'

interface TenantEditFormProps {
  tenant: Tenant
  onFinish: (values: { displayName: string; description?: string }) => Promise<void>
}

export default function TenantEditForm({ tenant, onFinish }: TenantEditFormProps) {
  return (
    <ProForm
      initialValues={{
        displayName: tenant.displayName,
        description: tenant.description || '',
      }}
      onFinish={onFinish}
      submitter={{
        searchConfig: { submitText: '保存' },
        resetButtonProps: false,
      }}
    >
      <ProFormText
        name="displayName"
        label="显示名称"
        placeholder="请输入显示名称"
        rules={[
          { required: true, message: '请输入显示名称' },
          { max: 200, message: '显示名称最多 200 个字符' },
        ]}
      />
      <ProFormTextArea
        name="description"
        label="描述"
        placeholder="请输入租户描述（选填）"
        fieldProps={{ rows: 3 }}
      />
    </ProForm>
  )
}
