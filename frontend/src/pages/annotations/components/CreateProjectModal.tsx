import { useEffect, useMemo } from 'react'
import { App, Form, Input, Modal, Radio, Select, Space, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createAnnotationProject, getAnnotationTemplates } from '@/services/annotations'
import { getDatasets, getDatasetDetail } from '@/services/datasets'
import type { AnnotationProjectCreateRequest } from '@/types/annotation'

interface CreateProjectModalProps {
  open: boolean
  onClose: () => void
}

export default function CreateProjectModal({ open, onClose }: CreateProjectModalProps) {
  const [form] = Form.useForm<AnnotationProjectCreateRequest>()
  const { message } = App.useApp()
  const queryClient = useQueryClient()
  const selectedDatasetId = Form.useWatch('datasetId', form)
  const selectedTemplate = Form.useWatch('annotationType', form)

  const { data: templates } = useQuery({
    queryKey: ['annotationTemplates'],
    queryFn: getAnnotationTemplates,
    enabled: open,
  })

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
      message.success('标注项目创建成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProjects'] })
      handleClose()
    },
  })

  const handleClose = () => {
    form.resetFields()
    onClose()
  }

  useEffect(() => {
    if (!open) return
    if (form.getFieldValue('datasetVersionId')) {
      form.resetFields(['datasetVersionId'])
    }
  }, [selectedDatasetId, form, open])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      createMutation.mutate({
        ...values,
        name: values.name.trim(),
        description: values.description?.trim() || undefined,
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

  const selectedTemplateInfo = templates?.find((t) => t.key === selectedTemplate)

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
      width={640}
    >
      <Form form={form} layout="vertical" style={{ marginTop: 8 }}>
        <Form.Item
          label="项目名称"
          name="name"
          rules={[
            { required: true, message: '请输入项目名称' },
            { whitespace: true, message: '项目名称不能为空' },
          ]}
        >
          <Input placeholder="请输入标注项目名称" maxLength={200} showCount />
        </Form.Item>

        <Form.Item label="项目描述" name="description">
          <Input.TextArea
            placeholder="可选，描述标注项目的用途"
            rows={2}
            maxLength={500}
            showCount
          />
        </Form.Item>

        <Space style={{ width: '100%' }} direction="vertical" size="middle">
          <Form.Item
            label="数据集"
            name="datasetId"
            rules={[{ required: true, message: '请选择数据集' }]}
            style={{ marginBottom: 0 }}
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
            style={{ marginBottom: 0 }}
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
          label="标注模板"
          name="annotationType"
          rules={[{ required: true, message: '请选择标注模板' }]}
          style={{ marginTop: 16 }}
        >
          <Radio.Group style={{ width: '100%' }}>
            <Space wrap>
              {templates?.map((t) => (
                <Radio key={t.key} value={t.key}>
                  {t.label}
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        </Form.Item>

        {selectedTemplateInfo && (
          <div
            style={{
              padding: '12px 16px',
              background: 'var(--ant-color-bg-layout)',
              borderRadius: 8,
              marginBottom: 16,
            }}
          >
            <Typography.Text strong>{selectedTemplateInfo.label}</Typography.Text>
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0, marginTop: 4 }}>
              {selectedTemplateInfo.description}
            </Typography.Paragraph>
          </div>
        )}
      </Form>
    </Modal>
  )
}
