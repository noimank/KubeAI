import { useEffect, useMemo, useState } from 'react'
import { Alert, Button, Form, Input, Select, Space, Tag, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createAnnotationTemplate,
  getAnnotationTemplate,
  listAnnotationTemplateGroups,
  updateAnnotationTemplate,
} from '@/services/annotation-templates'
import { getMessageInstance } from '@/utils/messageHolder'
import { parseLabelConfig } from '@/pages/annotations/utils/parseLabelConfig'

interface TemplateBuilderProps {
  templateId?: string
  onSaved?: () => void
}

interface BuilderFormValues {
  name: string
  description?: string
  group: string
  tags?: string[]
}

export default function TemplateBuilder({ templateId, onSaved }: TemplateBuilderProps) {
  const [form] = Form.useForm<BuilderFormValues>()
  const queryClient = useQueryClient()
  const [xml, setXml] = useState<string>('')

  const isEdit = !!templateId

  const { data: detail } = useQuery({
    queryKey: ['annotationTemplate', templateId],
    queryFn: () => getAnnotationTemplate(templateId!),
    enabled: isEdit,
  })

  const { data: existingGroups } = useQuery({
    queryKey: ['annotationTemplateGroups'],
    queryFn: listAnnotationTemplateGroups,
    staleTime: 60_000,
  })

  useEffect(() => {
    if (!detail) return
    form.setFieldsValue({
      name: detail.name,
      description: detail.description ?? undefined,
      group: detail.group,
      tags: detail.tags,
    })
    setXml(detail.labelConfig)
  }, [detail, form])

  const preview = useMemo(() => parseLabelConfig(xml), [xml])

  const saveMutation = useMutation({
    mutationFn: async () => {
      const values = await form.validateFields()
      const parsed = parseLabelConfig(xml)
      if (parsed.error) throw new Error(parsed.error)
      if (parsed.controls.length === 0) throw new Error('XML 配置缺少标注控件')
      const groupValue = Array.isArray(values.group) ? values.group[0] : values.group
      if (isEdit) {
        await updateAnnotationTemplate(templateId!, {
          name: values.name.trim(),
          description: values.description?.trim() || undefined,
          labelConfig: xml,
          tags: values.tags ?? [],
          group: groupValue || '其他',
        })
      } else {
        await createAnnotationTemplate({
          name: values.name.trim(),
          description: values.description?.trim() || undefined,
          labelConfig: xml,
          tags: values.tags ?? [],
          group: groupValue || '其他',
        })
      }
    },
    onSuccess: () => {
      getMessageInstance()?.success(isEdit ? '模板已更新' : '模板已创建')
      queryClient.invalidateQueries({ queryKey: ['annotationTemplates'] })
      queryClient.invalidateQueries({ queryKey: ['annotationTemplateGroups'] })
      onSaved?.()
    },
    onError: (e: Error) => {
      getMessageInstance()?.error(e.message ?? '保存失败')
    },
  })

  const groupOptions = (existingGroups ?? []).map((g) => ({ value: g, label: g }))

  return (
    <Form
      form={form}
      layout="vertical"
      initialValues={{ group: '其他', tags: [] }}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
        {/* 左侧: 基本字段 + XML 编辑 */}
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <Form.Item
            label="模板名称"
            name="name"
            rules={[
              { required: true, message: '请输入模板名称' },
              { min: 3, max: 200, message: '长度 3-200' },
            ]}
          >
            <Input placeholder="例如: 车辆目标检测" maxLength={200} showCount />
          </Form.Item>

          <Form.Item label="描述" name="description">
            <Input.TextArea rows={2} maxLength={500} showCount />
          </Form.Item>

          <Form.Item
            label="所属分组"
            name="group"
            rules={[{ required: true, message: '请输入或选择分组' }]}
          >
            <Select
              mode="tags"
              maxCount={1}
              placeholder="选择已有分组或输入新分组名"
              options={groupOptions}
            />
          </Form.Item>

          <Form.Item
            label="标签"
            name="tags"
            tooltip="便于搜索，如: 图像, 检测"
          >
            <Select mode="tags" placeholder="回车添加标签" />
          </Form.Item>

          <Form.Item
            label="Label Studio XML 配置"
            required
            validateStatus={preview.error ? 'error' : ''}
            help={preview.error}
          >
            <Input.TextArea
              rows={14}
              value={xml}
              onChange={(e) => setXml(e.target.value)}
              spellCheck={false}
              placeholder={`<View>
  <Image name="image" value="$image"/>
  <Choices name="choice" toName="image" choice="single-radio">
    <Choice value="类别1"/>
    <Choice value="类别2"/>
  </Choices>
</View>`}
            />
          </Form.Item>

          <Button
            type="primary"
            loading={saveMutation.isPending}
            onClick={() => saveMutation.mutate()}
          >
            {isEdit ? '保存' : '创建'}
          </Button>
        </Space>

        {/* 右侧: 预览 */}
        <Space direction="vertical" size="middle" style={{ width: '100%' }}>
          <div
            style={{
              padding: '8px 12px',
              borderRadius: 6,
              background: 'var(--ant-color-fill-tertiary)',
            }}
          >
            <Typography.Text strong>实时预览</Typography.Text>
          </div>

          {xml ? (
            preview.error ? (
              <Alert type="error" message={preview.error} />
            ) : (
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                <Typography.Text type="secondary">
                  数据标签: {preview.objects.map((o) => o.tag).join(', ') || '-'}
                </Typography.Text>
                <Typography.Text type="secondary">
                  控件:{' '}
                  {preview.controls
                    .map((c) => `${c.tag} → ${c.toName}`)
                    .join(', ') || '-'}
                </Typography.Text>
                <Typography.Text type="secondary">
                  标注类型: {preview.controls[0]?.type ?? '-'}
                </Typography.Text>
                <div>
                  {preview.controls.map((c) =>
                    c.choices.length > 0 ? (
                      <Space key={c.name} wrap style={{ marginTop: 8 }}>
                        {c.choices.map((choice) => (
                          <Tag
                            key={choice.value}
                            color={choice.background || 'blue'}
                          >
                            {choice.value}
                          </Tag>
                        ))}
                      </Space>
                    ) : null,
                  )}
                </div>
              </Space>
            )
          ) : (
            <Typography.Text type="secondary">尚未填写 XML 配置</Typography.Text>
          )}
        </Space>
      </div>
    </Form>
  )
}
