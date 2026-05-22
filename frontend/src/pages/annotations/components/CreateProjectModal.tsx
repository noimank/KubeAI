import { useEffect, useMemo } from 'react'
import { Button, Form, Input, Modal, Select, Space, Tag, Typography } from 'antd'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createAnnotationProject } from '@/services/annotations'
import { getDatasets, getDatasetDetail } from '@/services/datasets'
import { getMessageInstance } from '@/utils/messageHolder'
import type { AnnotationProjectCreateRequest } from '@/types/annotation'

interface CreateProjectModalProps {
  open: boolean
  onClose: () => void
}

type TaskType =
  | 'image_classification'
  | 'object_detection'
  | 'image_segmentation'
  | 'text_classification'
  | 'text_transcription'
  | 'audio_classification'
  | 'video_classification'

interface LabelOption {
  value: string
  color?: string
}

interface TaskTypeConfig {
  key: TaskType
  label: string
  description: string
  objectTag: 'Image' | 'Text' | 'Audio' | 'Video'
  objectName: string
  field: string
  controlTag: 'Choices' | 'RectangleLabels' | 'PolygonLabels' | 'TextArea'
  controlName: string
  defaultLabels: LabelOption[]
  needsLabels: boolean
  choiceMode?: 'single-radio' | 'multiple'
}

interface CreateProjectFormValues {
  name: string
  description?: string
  datasetId: string
  datasetVersionId: string
  taskType: TaskType
  choiceMode?: 'single-radio' | 'multiple'
  labels?: LabelOption[]
}

const LABEL_COLORS = ['#1677FF', '#52C41A', '#FAAD14', '#FF4D4F', '#722ED1', '#13C2C2', '#EB2F96']

const TASK_TYPES: TaskTypeConfig[] = [
  {
    key: 'image_classification',
    label: '图像分类',
    description: '给每张图片选择一个或多个类别。',
    objectTag: 'Image',
    objectName: 'image',
    field: 'image',
    controlTag: 'Choices',
    controlName: 'choice',
    defaultLabels: [{ value: '类别1' }, { value: '类别2' }],
    needsLabels: true,
    choiceMode: 'single-radio',
  },
  {
    key: 'object_detection',
    label: '目标检测',
    description: '在图片中绘制矩形框并标记目标类别。',
    objectTag: 'Image',
    objectName: 'image',
    field: 'image',
    controlTag: 'RectangleLabels',
    controlName: 'label',
    defaultLabels: [
      { value: '目标1', color: LABEL_COLORS[0] },
      { value: '目标2', color: LABEL_COLORS[1] },
    ],
    needsLabels: true,
  },
  {
    key: 'image_segmentation',
    label: '图像分割',
    description: '用多边形精确圈选图片中的目标区域。',
    objectTag: 'Image',
    objectName: 'image',
    field: 'image',
    controlTag: 'PolygonLabels',
    controlName: 'label',
    defaultLabels: [
      { value: '区域1', color: LABEL_COLORS[0] },
      { value: '区域2', color: LABEL_COLORS[1] },
    ],
    needsLabels: true,
  },
  {
    key: 'text_classification',
    label: '文本分类',
    description: '给文本选择情感、意图、主题等类别。',
    objectTag: 'Text',
    objectName: 'text',
    field: 'text',
    controlTag: 'Choices',
    controlName: 'sentiment',
    defaultLabels: [{ value: '正面' }, { value: '负面' }, { value: '中性' }],
    needsLabels: true,
    choiceMode: 'single-radio',
  },
  {
    key: 'text_transcription',
    label: '文本填写',
    description: '填写摘要、改写、问答等开放式标注结果。',
    objectTag: 'Text',
    objectName: 'text',
    field: 'text',
    controlTag: 'TextArea',
    controlName: 'answer',
    defaultLabels: [],
    needsLabels: false,
  },
  {
    key: 'audio_classification',
    label: '音频分类',
    description: '给音频片段选择事件、情绪或质检类别。',
    objectTag: 'Audio',
    objectName: 'audio',
    field: 'audio',
    controlTag: 'Choices',
    controlName: 'choice',
    defaultLabels: [{ value: '类别1' }, { value: '类别2' }],
    needsLabels: true,
    choiceMode: 'single-radio',
  },
  {
    key: 'video_classification',
    label: '视频分类',
    description: '给视频选择内容审核或场景类别。',
    objectTag: 'Video',
    objectName: 'video',
    field: 'video',
    controlTag: 'Choices',
    controlName: 'choice',
    defaultLabels: [{ value: '类别1' }, { value: '类别2' }],
    needsLabels: true,
    choiceMode: 'single-radio',
  },
]

const TASK_TYPE_MAP = Object.fromEntries(TASK_TYPES.map((item) => [item.key, item])) as Record<
  TaskType,
  TaskTypeConfig
>

function escapeXml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

function buildLabelConfig(
  typeConfig: TaskTypeConfig,
  labels: LabelOption[],
  choiceMode?: string,
): string {
  const dataTag = `  <${typeConfig.objectTag} name="${typeConfig.objectName}" value="$${typeConfig.field}"/>`
  const controlAttrs = [
    `name="${typeConfig.controlName}"`,
    `toName="${typeConfig.objectName}"`,
    typeConfig.controlTag === 'Choices'
      ? `choice="${choiceMode || typeConfig.choiceMode || 'single-radio'}"`
      : '',
  ]
    .filter(Boolean)
    .join(' ')

  if (typeConfig.controlTag === 'TextArea') {
    return `<View>
${dataTag}
  <TextArea ${controlAttrs} editable="true" maxSubmissions="1"/>
</View>`
  }

  const childTag = typeConfig.controlTag === 'Choices' ? 'Choice' : 'Label'
  const labelLines = labels
    .map((label, index) => {
      const color = label.color || LABEL_COLORS[index % LABEL_COLORS.length]
      const colorAttr = childTag === 'Label' ? ` background="${color}"` : ''
      return `    <${childTag} value="${escapeXml(label.value.trim())}"${colorAttr}/>`
    })
    .join('\n')

  return `<View>
${dataTag}
  <${typeConfig.controlTag} ${controlAttrs}>
${labelLines}
  </${typeConfig.controlTag}>
</View>`
}

export default function CreateProjectModal({ open, onClose }: CreateProjectModalProps) {
  const [form] = Form.useForm<CreateProjectFormValues>()
  const queryClient = useQueryClient()
  const selectedDatasetId = Form.useWatch('datasetId', form)
  const selectedTaskType = Form.useWatch('taskType', form) || 'image_classification'
  const labels = Form.useWatch('labels', form) ?? []
  const typeConfig = TASK_TYPE_MAP[selectedTaskType]

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

  const createMutation = useMutation({
    mutationFn: createAnnotationProject,
    onSuccess: () => {
      getMessageInstance()?.success('标注项目创建成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProjects'] })
      handleClose()
    },
  })

  const handleClose = () => {
    onClose()
  }

  useEffect(() => {
    if (!open) return
    if (form.getFieldValue('datasetVersionId')) {
      form.resetFields(['datasetVersionId'])
    }
  }, [selectedDatasetId, form, open])

  const handleTaskTypeChange = (taskType: TaskType) => {
    const nextType = TASK_TYPE_MAP[taskType]
    form.setFieldsValue({
      taskType,
      labels: nextType.defaultLabels,
      choiceMode: nextType.choiceMode,
    })
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const nextType = TASK_TYPE_MAP[values.taskType]
      const nextLabels = nextType.needsLabels ? (values.labels ?? []) : []
      const labelConfig = buildLabelConfig(nextType, nextLabels, values.choiceMode)
      const request: AnnotationProjectCreateRequest = {
        name: values.name.trim(),
        description: values.description?.trim() || undefined,
        datasetId: values.datasetId,
        datasetVersionId: values.datasetVersionId,
        labelConfig,
      }
      createMutation.mutate(request)
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

  return (
    <Modal
      title="创建标注项目"
      open={open}
      onCancel={handleClose}
      onOk={handleSubmit}
      confirmLoading={createMutation.isPending}
      okText="创建项目"
      cancelText="取消"
      destroyOnHidden
      width={880}
    >
      <Form
        form={form}
        layout="vertical"
        style={{ marginTop: 8 }}
        initialValues={{
          taskType: 'image_classification',
          labels: TASK_TYPE_MAP.image_classification.defaultLabels,
          choiceMode: TASK_TYPE_MAP.image_classification.choiceMode,
        }}
      >
        <Space style={{ width: '100%' }} direction="vertical" size="middle">
          <Form.Item
            label="项目名称"
            name="name"
            rules={[
              { required: true, message: '请输入项目名称' },
              { whitespace: true, message: '项目名称不能为空' },
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

          <Form.Item
            label="标注任务"
            name="taskType"
            rules={[{ required: true, message: '请选择标注任务' }]}
            style={{ marginBottom: 0 }}
          >
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 8,
              }}
            >
              {TASK_TYPES.map((taskType) => {
                const active = selectedTaskType === taskType.key
                return (
                  <button
                    key={taskType.key}
                    type="button"
                    onClick={() => handleTaskTypeChange(taskType.key)}
                    style={{
                      textAlign: 'left',
                      padding: '10px 12px',
                      borderRadius: 6,
                      border: active
                        ? '1px solid var(--ant-color-primary)'
                        : '1px solid var(--ant-color-border)',
                      background: active
                        ? 'var(--ant-color-primary-bg)'
                        : 'var(--ant-color-bg-container)',
                      cursor: 'pointer',
                    }}
                  >
                    <Typography.Text strong>{taskType.label}</Typography.Text>
                    <Typography.Paragraph
                      type="secondary"
                      style={{ fontSize: 12, margin: '4px 0 0' }}
                      ellipsis={{ rows: 2 }}
                    >
                      {taskType.description}
                    </Typography.Paragraph>
                  </button>
                )
              })}
            </div>
          </Form.Item>

          {typeConfig.controlTag === 'Choices' && (
            <Form.Item label="选择方式" name="choiceMode" style={{ marginBottom: 0 }}>
              <Select
                style={{ width: 180 }}
                options={[
                  { label: '单选', value: 'single-radio' },
                  { label: '多选', value: 'multiple' },
                ]}
              />
            </Form.Item>
          )}

          {typeConfig.needsLabels && (
            <Form.List
              name="labels"
              rules={[
                {
                  validator: async (_, value: LabelOption[] | undefined) => {
                    if (!value || value.length === 0) throw new Error('请至少添加一个标签')
                    const names = value.map((item) => item?.value?.trim()).filter(Boolean)
                    if (names.length !== value.length) throw new Error('标签名称不能为空')
                    if (new Set(names).size !== names.length) throw new Error('标签名称不能重复')
                  },
                },
              ]}
            >
              {(fields, { add, remove }, { errors }) => (
                <Form.Item label="标签体系" required style={{ marginBottom: 0 }}>
                  <Space direction="vertical" size="small" style={{ width: '100%' }}>
                    {fields.map((field, index) => {
                      const { key, ...fieldProps } = field
                      return (
                        <Space key={key} align="baseline" style={{ width: '100%' }}>
                          <Tag
                            color={
                              labels[index]?.color || LABEL_COLORS[index % LABEL_COLORS.length]
                            }
                          >
                            {index + 1}
                          </Tag>
                          <Form.Item
                            {...fieldProps}
                            name={[field.name, 'value']}
                            rules={[{ required: true, message: '请输入标签名称' }]}
                            style={{ flex: 1, marginBottom: 0 }}
                          >
                            <Input placeholder="标签名称" />
                          </Form.Item>
                          <Form.Item name={[field.name, 'color']} hidden>
                            <Input />
                          </Form.Item>
                          <Button
                            icon={<DeleteOutlined />}
                            disabled={fields.length <= 1}
                            onClick={() => remove(field.name)}
                          />
                        </Space>
                      )
                    })}
                    <Button
                      icon={<PlusOutlined />}
                      onClick={() =>
                        add({
                          value: `标签${fields.length + 1}`,
                          color: LABEL_COLORS[fields.length % LABEL_COLORS.length],
                        })
                      }
                    >
                      添加标签
                    </Button>
                    <Form.ErrorList errors={errors} />
                  </Space>
                </Form.Item>
              )}
            </Form.List>
          )}
        </Space>
      </Form>
    </Modal>
  )
}
