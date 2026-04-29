import { ProFormText, ProFormTextArea } from '@ant-design/pro-components'
import { ProForm } from '@ant-design/pro-components'

interface TenantCreateFormProps {
  onFinish: (values: { name: string; displayName: string; description?: string }) => Promise<void>
}

export default function TenantCreateForm({ onFinish }: TenantCreateFormProps) {
  return (
    <ProForm
      onFinish={onFinish}
      submitter={{
        searchConfig: { submitText: '创建' },
        resetButtonProps: false,
      }}
    >
      <ProFormText
        name="name"
        label="租户名称"
        placeholder="请输入租户名称（英文）"
        rules={[
          { required: true, message: '请输入租户名称' },
          { min: 2, message: '租户名称至少 2 个字符' },
          { max: 100, message: '租户名称最多 100 个字符' },
          { pattern: /^[a-z0-9][a-z0-9-]*[a-z0-9]$/, message: '仅支持小写字母、数字和中划线' },
        ]}
      />
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
