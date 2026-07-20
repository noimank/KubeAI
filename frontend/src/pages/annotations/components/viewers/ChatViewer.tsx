import { useCallback, useMemo } from 'react'
import { Tag, Typography } from 'antd'
import type { AnnotationTask } from '@/types/annotation'
import type { LabelStudioObjectConfig } from '../../utils/parseLabelConfig'
import type { Region } from '../../hooks/useAnnotationRegions'

interface ChatViewerProps {
  task: AnnotationTask
  objectConfig: LabelStudioObjectConfig
  regions: Region[]
  selectedRegionId: string | null
  onAddRegion: (region: Region) => void
  onSelectRegion: (id: string | null) => void
  readOnly: boolean
}

interface Message {
  role: string
  content: string
}

function toMessages(value: unknown): Message[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    const obj = (item ?? {}) as Record<string, unknown>
    const role = (obj.role as string) ?? (obj.author as string) ?? (obj.name as string) ?? 'message'
    const content = (obj.content as string) ?? (obj.text as string) ?? ''
    return { role, content }
  })
}

/**
 * Chat 对象查看器 —— 消息即区域（RLHF 评估）。
 * 点击一条消息选中它（创建/选中 message region），perRegion 控件挂载其上。
 * 选中消息的高亮 + role 用于 whenRole 条件（由 workspace 从 region.value.role 提取）。
 */
export default function ChatViewer({
  task,
  objectConfig,
  regions,
  selectedRegionId,
  onAddRegion,
  onSelectRegion,
  readOnly,
}: ChatViewerProps) {
  const field = objectConfig.field || 'chat'
  const messages = useMemo(() => toMessages(task.data?.[field]), [task.data, field])

  const regionIdFor = useCallback(
    (messageId: string) => `${objectConfig.name}:${messageId}`,
    [objectConfig.name],
  )

  const handleClick = useCallback(
    (messageId: string, role: string) => {
      if (readOnly) return
      const id = regionIdFor(messageId)
      const existing = regions.find((r) => r.id === id)
      if (existing) {
        onSelectRegion(selectedRegionId === id ? null : id)
        return
      }
      onAddRegion({
        id,
        fromName: objectConfig.name,
        value: { kind: 'message', messageId, role },
        perRegionResults: {},
      })
      onSelectRegion(id)
    },
    [
      readOnly,
      regions,
      selectedRegionId,
      regionIdFor,
      objectConfig.name,
      onAddRegion,
      onSelectRegion,
    ],
  )

  if (messages.length === 0) {
    return <Typography.Text type="secondary">无对话数据</Typography.Text>
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 4 }}>
      {!readOnly && (
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          点击消息可对其逐条评估（perRegion 控件将出现在侧栏）。
        </Typography.Text>
      )}
      {messages.map((m, i) => {
        const messageId = String(i)
        const id = regionIdFor(messageId)
        const selected = selectedRegionId === id
        const isUser = m.role === 'user' || m.role === 'human'
        return (
          <div
            key={messageId}
            onClick={() => handleClick(messageId, m.role)}
            style={{
              alignSelf: isUser ? 'flex-start' : 'flex-end',
              maxWidth: '80%',
              cursor: readOnly ? 'default' : 'pointer',
              padding: '8px 12px',
              borderRadius: 8,
              background: selected
                ? 'var(--ant-color-primary-bg)'
                : isUser
                  ? 'var(--ant-color-fill-tertiary)'
                  : 'var(--ant-color-bg-container)',
              border: selected
                ? '2px solid var(--ant-color-primary)'
                : '1px solid var(--ant-color-border)',
            }}
          >
            <Tag color={isUser ? 'blue' : 'green'} style={{ marginBottom: 4 }}>
              {m.role}
            </Tag>
            <div style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{m.content}</div>
          </div>
        )
      })}
    </div>
  )
}
