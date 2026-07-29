import { Form, Input, Select, Space, Typography } from 'antd'
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons'
import type { BusinessConfig } from '@/types/business-config'

export interface EnvVarEditorProps {
  /** Form.List name, defaults to 'envVars' */
  name?: string
  /** Placeholder for key input */
  keyPlaceholder?: string
  /** Placeholder for value input */
  valuePlaceholder?: string
  /** Text for the add button */
  addButtonText?: string
  /** Available business config presets. When provided, shows a "load from preset" dropdown. */
  presets?: BusinessConfig[]
  /** Whether presets are loading */
  presetsLoading?: boolean
}

export default function EnvVarEditor({
  name = 'envVars',
  keyPlaceholder = '变量名',
  valuePlaceholder = '变量值',
  addButtonText = '+ 添加环境变量',
  presets,
  presetsLoading = false,
}: EnvVarEditorProps) {
  const form = Form.useFormInstance()

  const handlePresetSelect = (presetId: string) => {
    const preset = presets?.find((p) => p.id === presetId)
    if (!preset) return

    // 合并: 预设值在后，不覆盖已填写的同名 key
    const existing: { key: string; value: string }[] = form.getFieldValue(name) ?? []
    const existingKeys = new Set(existing.map((e) => e.key?.trim()).filter(Boolean))
    const newEntries = Object.entries(preset.envVars)
      .filter(([k]) => !existingKeys.has(k))
      .map(([key, value]) => ({ key, value }))
    form.setFieldValue(name, [...existing, ...newEntries])
  }

  return (
    <div>
      {presets && presets.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <Space>
            <Typography.Text type="secondary" style={{ whiteSpace: 'nowrap' }}>
              从业务配置加载:
            </Typography.Text>
            <Select
              allowClear
              showSearch
              style={{ minWidth: 200 }}
              placeholder="选择业务配置"
              loading={presetsLoading}
              optionFilterProp="label"
              onChange={handlePresetSelect}
              options={presets.map((p) => ({
                value: p.id,
                label: p.name,
              }))}
            />
          </Space>
        </div>
      )}
      <Form.List name={name}>
        {(fields, { add, remove }) => (
          <>
            {fields.map(({ key, name: fieldName, ...restField }) => (
              <Space key={key} style={{ display: 'flex', marginBottom: 8 }} align="baseline">
                <Form.Item
                  {...restField}
                  name={[fieldName, 'key']}
                  rules={[{ required: true, message: `请输入${keyPlaceholder}` }]}
                  style={{ width: 200, marginBottom: 0 }}
                >
                  <Input placeholder={keyPlaceholder} />
                </Form.Item>
                <Form.Item
                  {...restField}
                  name={[fieldName, 'value']}
                  style={{ width: 280, marginBottom: 0 }}
                >
                  <Input placeholder={valuePlaceholder} />
                </Form.Item>
                <DeleteOutlined
                  onClick={() => remove(fieldName)}
                  style={{ color: '#ff4d4f', cursor: 'pointer', fontSize: 14 }}
                />
              </Space>
            ))}
            <Form.Item>
              <button
                type="button"
                className="ant-btn ant-btn-dashed"
                style={{ width: '100%' }}
                onClick={() => add({ key: '', value: '' })}
              >
                <PlusOutlined /> {addButtonText}
              </button>
            </Form.Item>
          </>
        )}
      </Form.List>
    </div>
  )
}
