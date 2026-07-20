import { Card, Modal, Space, Tag, Typography } from 'antd'

const HOTKEYS: Array<{ key: string; label: string }> = [
  { key: '1-9', label: '选择标签' },
  { key: 'Enter', label: '提交当前标注 (Ctrl+Enter)' },
  { key: '← / →', label: '上一个 / 下一个任务' },
  { key: 'Ctrl+Z', label: '撤销' },
  { key: 'Space (按住)', label: '临时平移画布' },
  { key: '滚轮', label: '以鼠标为锚点缩放' },
]

export default function HotkeyHelpModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  return (
    <Modal open={open} title="快捷键" footer={null} onCancel={onClose}>
      <Card size="small">
        <Space direction="vertical" style={{ width: '100%' }}>
          {HOTKEYS.map((h) => (
            <Space key={h.key} style={{ width: '100%', justifyContent: 'space-between' }}>
              <Typography.Text type="secondary">{h.label}</Typography.Text>
              <Tag>{h.key}</Tag>
            </Space>
          ))}
        </Space>
      </Card>
    </Modal>
  )
}
