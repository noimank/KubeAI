import { useEffect, useMemo, useState } from 'react'
import { Alert, Form, Input, Modal, Select, Space, Tag } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createAnnotationProject } from '@/services/annotations'
import {
  getAnnotationTemplate,
  listAnnotationTemplateGroups,
  listAnnotationTemplates,
} from '@/services/annotation-templates'
import { getDatasets, getDatasetDetail } from '@/services/datasets'
import { getMessageInstance } from '@/utils/messageHolder'

/** Extract unique $field references from object tags in a label config XML string. */
function extractObjectFields(labelConfig: string): string[] {
  const seen = new Set<string>()
  // Match value attributes on data-object tags: <Text value="$fieldName"/>, <Image value="$img"/>, etc.
  const OBJECT_TAGS = new Set([
    'Image',
    'Text',
    'Audio',
    'Video',
    'HyperText',
    'PDF',
    'Pdf',
    'Paragraphs',
    'TimeSeries',
    'Table',
    'List',
    'PagedView',
    'Chat',
  ])
  const tagRe = new RegExp(`<(${[...OBJECT_TAGS].join('|')})[^>]*value\\s*=\\s*"\\$([^"]+)"`, 'gi')
  let m: RegExpExecArray | null
  while ((m = tagRe.exec(labelConfig)) !== null) {
    seen.add(m[2])
  }
  return [...seen]
}

interface CreateProjectModalProps {
  open: boolean
  onClose: () => void
}

interface CreateProjectFormValues {
  name: string
  description?: string
  datasetId: string
  datasetVersionId: string
  templateGroup?: string
  templateId: string
}

export default function CreateProjectModal({ open, onClose }: CreateProjectModalProps) {
  const [form] = Form.useForm<CreateProjectFormValues>()
  const queryClient = useQueryClient()
  const selectedDatasetId = Form.useWatch('datasetId', form)
  const selectedGroup = Form.useWatch('templateGroup', form)
  const selectedTemplateId: string | undefined = Form.useWatch('templateId', form)
  const [fieldHint, setFieldHint] = useState<string[]>([])

  const { data: datasetsData } = useQuery({
    queryKey: ['datasets', 1, 100],
    queryFn: () => getDatasets({ current: 1, pageSize: 100 }),
    enabled: open,
  })

  const { data: datasetDetail, isFetching: isDatasetDetailFetching } = useQuery({
    queryKey: ['datasetDetail', selectedDatasetId],
    queryFn: () => getDatasetDetail(selectedDatasetId!),
    enabled: open && !!selectedDatasetId,
  })

  const { data: groups } = useQuery({
    queryKey: ['annotationTemplateGroups'],
    queryFn: listAnnotationTemplateGroups,
    enabled: open,
  })

  const { data: templatesData } = useQuery({
    queryKey: ['annotationTemplates', 'byGroup', selectedGroup],
    queryFn: () => listAnnotationTemplates({ current: 1, pageSize: 200, group: selectedGroup! }),
    enabled: open && !!selectedGroup,
  })

  // Fetch template detail to show multi-object field hints
  useQuery({
    queryKey: ['annotationTemplate', selectedTemplateId],
    queryFn: () => getAnnotationTemplate(selectedTemplateId!),
    enabled: open && !!selectedTemplateId,
    onSettled: (data) => {
      const fields = data?.labelConfig ? extractObjectFields(data.labelConfig) : []
      setFieldHint(fields.length > 1 ? fields : [])
    },
  })

  const createMutation = useMutation({
    mutationFn: createAnnotationProject,
    onSuccess: () => {
      getMessageInstance()?.success('标注项目创建成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProjects'] })
      onClose()
    },
    onError: (e: Error) => {
      getMessageInstance()?.error(e.message ?? '创建失败')
    },
  })

  useEffect(() => {
    if (!open) return
    form.resetFields()
  }, [open, form])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      createMutation.mutate({
        name: values.name.trim(),
        description: values.description?.trim() || undefined,
        datasetId: values.datasetId,
        datasetVersionId: values.datasetVersionId,
        templateId: values.templateId,
      })
    } catch {
      // validation error
    }
  }

  const datasetOptions = useMemo(
    () =>
      datasetsData?.items?.map((ds) => ({
        value: ds.id,
        label: ds.displayName || ds.name,
      })) ?? [],
    [datasetsData?.items],
  )

  const versionOptions = useMemo(
    () =>
      datasetDetail?.versions?.map((v) => ({
        value: v.id,
        label: `v${v.versionNumber}${v.description ? ` - ${v.description}` : ''}`,
      })) ?? [],
    [datasetDetail?.versions],
  )

  const groupOptions = useMemo(() => (groups ?? []).map((g) => ({ value: g, label: g })), [groups])

  const templateOptions = useMemo(
    () =>
      (templatesData?.items ?? []).map((t) => ({
        value: t.id,
        label: t.name,
      })),
    [templatesData?.items],
  )

  return (
    <Modal
      title="创建标注项目"
      open={open}
      onCancel={onClose}
      onOk={handleSubmit}
      confirmLoading={createMutation.isPending}
      okText="创建项目"
      cancelText="取消"
      destroyOnHidden
      width={720}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
        <Space style={{ width: '100%' }} direction="vertical" size="middle">
          <Form.Item
            label="项目名称"
            name="name"
            rules={[
              { required: true, message: '请输入项目名称' },
              { whitespace: true, message: '项目名称不能为空' },
              { min: 3, message: '项目名称至少 3 个字符' },
            ]}
            style={{ marginBottom: 0 }}
          >
            <Input placeholder="请输入标注项目名称" maxLength={200} showCount />
          </Form.Item>

          <Form.Item label="项目描述" name="description" style={{ marginBottom: 0 }}>
            <Input.TextArea
              placeholder="可选，描述标注规则或验收标准"
              rows={2}
              maxLength={500}
              showCount
            />
          </Form.Item>

          <Space style={{ width: '100%' }} size="middle" align="start">
            <Form.Item
              label="数据集"
              name="datasetId"
              rules={[{ required: true, message: '请选择数据集' }]}
              style={{ flex: 1, marginBottom: 0 }}
            >
              <Select
                placeholder="选择数据集"
                showSearch
                optionFilterProp="label"
                options={datasetOptions}
                onChange={() => form.resetFields(['datasetVersionId'])}
              />
            </Form.Item>

            <Form.Item
              label="数据集版本"
              name="datasetVersionId"
              rules={[{ required: true, message: '请选择数据集版本' }]}
              style={{ flex: 1, marginBottom: 0 }}
            >
              <Select
                placeholder={selectedDatasetId ? '选择版本' : '请先选择数据集'}
                disabled={!selectedDatasetId}
                loading={isDatasetDetailFetching}
                notFoundContent={selectedDatasetId ? '暂无版本' : null}
                options={versionOptions}
              />
            </Form.Item>
          </Space>

          <Space style={{ width: '100%' }} size="middle" align="start">
            <Form.Item
              label="模板分组"
              name="templateGroup"
              rules={[{ required: true, message: '请选择模板分组' }]}
              style={{ flex: 1, marginBottom: 0 }}
            >
              <Select
                placeholder="选择模板分组"
                options={groupOptions}
                notFoundContent="暂无分组"
                onChange={() => form.resetFields(['templateId'])}
              />
            </Form.Item>

            <Form.Item
              label="标注模板"
              name="templateId"
              rules={[{ required: true, message: '请选择标注模板' }]}
              style={{ flex: 1, marginBottom: 0 }}
              extra="如无可用模板，请到上方「标注模板」标签页创建"
            >
              <Select
                placeholder={selectedGroup ? '选择模板' : '请先选择分组'}
                disabled={!selectedGroup}
                showSearch
                optionFilterProp="label"
                options={templateOptions}
                notFoundContent={selectedGroup ? '该分组下暂无模板' : '请先选择分组'}
              />
            </Form.Item>
          </Space>

          {fieldHint.length > 0 && (
            <Alert
              type="info"
              showIcon
              message="多字段标注模板"
              description={
                <span>
                  该模板需要结构化数据文件 (JSON / JSONL / CSV)。每条记录需包含以下{' '}
                  {fieldHint.length} 个字段：
                  <Space wrap style={{ marginLeft: 8 }}>
                    {fieldHint.map((f) => (
                      <Tag key={f} color="blue">
                        ${f}
                      </Tag>
                    ))}
                  </Space>
                  <br />
                  <span style={{ color: '#faad14', fontSize: 12 }}>
                    非结构化文件（图片、音频、纯文本等）将自动跳过。
                  </span>
                </span>
              }
              style={{ marginBottom: 0 }}
            />
          )}
        </Space>
      </Form>
    </Modal>
  )
}
