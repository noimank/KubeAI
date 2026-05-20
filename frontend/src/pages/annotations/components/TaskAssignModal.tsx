import { useEffect } from 'react'
import { Form, Modal, Select, InputNumber, Space, Typography } from 'antd'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuthStore } from '@/stores/authStore'
import { listMembers } from '@/services/tenants'
import { assignAnnotationTasks, batchAssignAnnotationTasks } from '@/services/annotations'
import { getMessageInstance } from '@/utils/messageHolder'

const { Text } = Typography

interface TaskAssignModalProps {
  open: boolean
  onClose: () => void
  projectId: string
  mode: 'assign' | 'batch'
  selectedTaskIds?: string[]
  unassignedCount?: number
  title?: string
}

export default function TaskAssignModal({
  open,
  onClose,
  projectId,
  mode,
  selectedTaskIds = [],
  unassignedCount = 0,
  title,
}: TaskAssignModalProps) {
  const [form] = Form.useForm()
  const queryClient = useQueryClient()
  const tenantId = useAuthStore((s) => s.user?.tenantId)

  const { data: membersData } = useQuery({
    queryKey: ['tenantMembers', tenantId],
    queryFn: () => listMembers(tenantId!),
    enabled: !!tenantId && open,
  })

  const members = membersData?.data ?? []

  const assignMutation = useMutation({
    mutationFn: (values: { userId: string }) =>
      assignAnnotationTasks(projectId, { taskIds: selectedTaskIds, userId: values.userId }),
    onSuccess: (res) => {
      getMessageInstance()?.success(res.message || '分配成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProjectTasks', projectId] })
      handleClose()
    },
  })

  const batchMutation = useMutation({
    mutationFn: (values: { userIds: string[]; tasksPerUser: number }) =>
      batchAssignAnnotationTasks(projectId, values),
    onSuccess: (res) => {
      getMessageInstance()?.success(res.message || '均匀分配成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProjectTasks', projectId] })
      handleClose()
    },
  })

  useEffect(() => {
    if (open) {
      form.resetFields()
    }
  }, [open, form])

  const handleClose = () => {
    form.resetFields()
    onClose()
  }

  const handleSubmit = async () => {
    const values = await form.validateFields()
    if (mode === 'assign') {
      assignMutation.mutate(values)
    } else {
      batchMutation.mutate(values)
    }
  }

  const loading = assignMutation.isPending || batchMutation.isPending

  if (mode === 'assign') {
    return (
      <Modal
        title={title || '分配任务'}
        open={open}
        onCancel={handleClose}
        onOk={handleSubmit}
        confirmLoading={loading}
        destroyOnHidden
      >
        <Text>已选中 {selectedTaskIds.length} 个任务</Text>
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item
            name="userId"
            label="分配给"
            rules={[{ required: true, message: '请选择成员' }]}
          >
            <Select
              placeholder="选择成员"
              options={members.map((m) => ({ label: `${m.username} (${m.role})`, value: m.id }))}
              showSearch
              optionFilterProp="label"
            />
          </Form.Item>
        </Form>
      </Modal>
    )
  }

  return (
    <Modal
      title="均匀分配任务"
      open={open}
      onCancel={handleClose}
      onOk={handleSubmit}
      confirmLoading={loading}
      destroyOnHidden
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Text>可分配任务数: {unassignedCount}</Text>
      </Space>
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item name="userIds" label="成员" rules={[{ required: true, message: '请选择成员' }]}>
          <Select
            mode="multiple"
            placeholder="选择成员"
            options={members.map((m) => ({ label: `${m.username} (${m.role})`, value: m.id }))}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>
        <Form.Item
          name="tasksPerUser"
          label="每人任务数"
          rules={[{ required: true, message: '请输入每人任务数' }]}
        >
          <InputNumber
            min={1}
            max={unassignedCount}
            style={{ width: '100%' }}
            placeholder="输入每人分配数量"
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
