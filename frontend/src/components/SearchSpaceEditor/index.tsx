import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { Button, Form, Input, InputNumber, Select, Space, Switch, Typography } from 'antd'
import type { SearchSpaceParamType } from '@/types/tuning'

const TYPE_OPTIONS: { label: string; value: SearchSpaceParamType }[] = [
  { label: '浮点数 (float)', value: 'float' },
  { label: '整数 (int)', value: 'int' },
  { label: '类别 (categorical)', value: 'categorical' },
  { label: '固定值 (fixed)', value: 'fixed' },
]

export interface SearchSpaceEditorProps {
  /** Form.List name, defaults to 'searchSpace' */
  name?: string
}

/** 编辑器行值。categorical 候选值以逗号分隔字符串存储，提交时再拆分。 */
export interface SearchSpaceRowValue {
  name?: string
  type?: SearchSpaceParamType
  low?: number
  high?: number
  log?: boolean
  /** categorical 候选值，逗号分隔字符串 */
  choices?: string
  /** fixed 固定值 */
  value?: string | number | boolean
}

function SearchSpaceRowFields({
  listName,
  fieldName,
  onRemove,
}: {
  listName: string
  fieldName: number
  onRemove: () => void
}) {
  const form = Form.useFormInstance()
  // useWatch 直读根 store (非 Field, 不经 Form.List 字段上下文前缀), 故需绝对路径 [listName, index, 'type'];
  // 而 Form.Item 的 name 在 Form.List 内会被自动前缀 listName, 故只写相对路径 [index, 'xxx'].
  const type: SearchSpaceParamType = Form.useWatch([listName, fieldName, 'type'], form)

  return (
    <Space style={{ display: 'flex', marginBottom: 8 }} align="baseline" wrap>
      <Form.Item
        name={[fieldName, 'name']}
        rules={[{ required: true, message: '请输入参数名' }]}
        style={{ width: 180, marginBottom: 0 }}
      >
        <Input placeholder="参数名" />
      </Form.Item>
      <Form.Item
        name={[fieldName, 'type']}
        rules={[{ required: true }]}
        style={{ width: 170, marginBottom: 0 }}
      >
        <Select options={TYPE_OPTIONS} placeholder="类型" />
      </Form.Item>

      {type === 'float' && (
        <>
          <Form.Item
            name={[fieldName, 'low']}
            rules={[{ required: true, message: '下限' }]}
            style={{ marginBottom: 0 }}
          >
            <InputNumber placeholder="下限" step="any" style={{ width: 100 }} />
          </Form.Item>
          <Form.Item
            name={[fieldName, 'high']}
            rules={[{ required: true, message: '上限' }]}
            style={{ marginBottom: 0 }}
          >
            <InputNumber placeholder="上限" step="any" style={{ width: 100 }} />
          </Form.Item>
          <Form.Item name={[fieldName, 'log']} valuePropName="checked" style={{ marginBottom: 0 }}>
            <Switch checkedChildren="log" unCheckedChildren="线性" />
          </Form.Item>
        </>
      )}

      {type === 'int' && (
        <>
          <Form.Item
            name={[fieldName, 'low']}
            rules={[{ required: true, message: '下限' }]}
            style={{ marginBottom: 0 }}
          >
            <InputNumber placeholder="下限" precision={0} style={{ width: 100 }} />
          </Form.Item>
          <Form.Item
            name={[fieldName, 'high']}
            rules={[{ required: true, message: '上限' }]}
            style={{ marginBottom: 0 }}
          >
            <InputNumber placeholder="上限" precision={0} style={{ width: 100 }} />
          </Form.Item>
          <Form.Item name={[fieldName, 'log']} valuePropName="checked" style={{ marginBottom: 0 }}>
            <Switch checkedChildren="log" unCheckedChildren="线性" />
          </Form.Item>
        </>
      )}

      {type === 'categorical' && (
        <Form.Item
          name={[fieldName, 'choices']}
          rules={[{ required: true, message: '请输入候选值' }]}
          style={{ minWidth: 260, marginBottom: 0 }}
        >
          <Input placeholder="候选值，用逗号分隔，如 adam,sgd" />
        </Form.Item>
      )}

      {type === 'fixed' && (
        <Form.Item
          name={[fieldName, 'value']}
          rules={[{ required: true, message: '请输入固定值' }]}
          style={{ marginBottom: 0 }}
        >
          <Input placeholder="固定值" style={{ width: 160 }} />
        </Form.Item>
      )}

      <DeleteOutlined
        onClick={onRemove}
        style={{ color: '#ff4d4f', cursor: 'pointer', fontSize: 14 }}
      />
    </Space>
  )
}

export default function SearchSpaceEditor({ name = 'searchSpace' }: SearchSpaceEditorProps) {
  return (
    <div>
      <Typography.Paragraph type="secondary" style={{ marginBottom: 12, fontSize: 12 }}>
        定义待调优的超参数搜索空间。调度器按此处范围采样，把采样值作为环境变量注入每个 trial
        的训练任务。
      </Typography.Paragraph>
      <Form.List name={name}>
        {(fields, { add, remove }) => (
          <>
            {fields.map(({ key, name: fieldName }) => (
              <SearchSpaceRowFields
                key={key}
                listName={name}
                fieldName={fieldName}
                onRemove={() => remove(fieldName)}
              />
            ))}
            <Form.Item>
              <Button type="dashed" onClick={() => add({})} block>
                <PlusOutlined /> 添加超参数
              </Button>
            </Form.Item>
          </>
        )}
      </Form.List>
    </div>
  )
}
