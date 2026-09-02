import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Space, Tag, Typography } from 'antd'
import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import { regionsOf } from '../utils/regions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'

/** Paragraphs 数据中的一条 utterance */
interface Utterance {
  author: string
  text: string
}

function toUtterances(value: unknown): Utterance[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    const obj = (item ?? {}) as Record<string, unknown>
    const author = (obj.author as string) ?? (obj.name as string) ?? (obj.role as string) ?? ''
    const text = (obj.text as string) ?? (obj.content as string) ?? ''
    return { author, text }
  })
}

/**
 * ParagraphLabels 标注器 —— 对话 utterance 内的文本 span 标注（槽位填充/实体）。
 * 选中某条 utterance 内的文本 → 确认 → 创建 paragraphspan region。
 */
export default function ParagraphLabelsAnnotator({
  task,
  objectConfig,
  controlConfig,
  readOnly = false,
  regions,
  onAddRegion,
  onDeleteRegion,
}: SpatialAnnotatorProps) {
  const field = objectConfig?.field || 'dialogue'
  const utterances = useMemo(() => toUtterances(task.data?.[field]), [task.data, field])
  const labels = useMemo(() => controlConfig.choices.map((c) => c.value), [controlConfig.choices])
  const [activeLabel, setActiveLabel] = useState<string | null>(labels[0] ?? null)
  const [pending, setPending] = useState<{
    paragraphId: string
    start: number
    end: number
    text: string
  } | null>(null)
  const textRefs = useRef<Map<string, HTMLPreElement>>(new Map())

  // 按 utterance 分组的 span 区域
  const spansByParagraph = useMemo(() => {
    const map = new Map<string, ReturnType<typeof regionsOf<'paragraphspan'>>>()
    for (const r of regionsOf(regions, controlConfig.name, 'paragraphspan')) {
      const arr = map.get(r.value.paragraphId) ?? []
      arr.push(r)
      map.set(r.value.paragraphId, arr)
    }
    return map
  }, [regions, controlConfig.name])

  useEffect(() => {
    setPending(null)
    setActiveLabel(labels[0] ?? null)
  }, [task.id, labels])

  const captureSelection = useCallback((paragraphId: string) => {
    const sel = window.getSelection()
    const textNode = textRefs.current.get(paragraphId)
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed || !textNode) {
      setPending(null)
      return
    }
    const range = sel.getRangeAt(0)
    if (!textNode.contains(range.startContainer) || !textNode.contains(range.endContainer)) {
      setPending(null)
      return
    }
    const pre = document.createRange()
    pre.selectNodeContents(textNode)
    pre.setEnd(range.startContainer, range.startOffset)
    const start = pre.toString().length
    const selectedText = sel.toString()
    if (!selectedText.trim()) {
      setPending(null)
      return
    }
    setPending({ paragraphId, start, end: start + selectedText.length, text: selectedText })
  }, [])

  const confirmSpan = useCallback(() => {
    if (!pending || !activeLabel) return
    onAddRegion({
      id: crypto.randomUUID(),
      fromName: controlConfig.name,
      label: activeLabel,
      value: {
        kind: 'paragraphspan',
        paragraphId: pending.paragraphId,
        start: pending.start,
        end: pending.end,
        text: pending.text,
      },
      perRegionResults: {},
    })
    setPending(null)
    window.getSelection()?.removeAllRanges()
  }, [pending, activeLabel, controlConfig.name, onAddRegion])

  const cancelSpan = useCallback(() => {
    setPending(null)
    window.getSelection()?.removeAllRanges()
  }, [])

  useEffect(() => {
    if (readOnly) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key === 'Enter' && pending) {
        e.preventDefault()
        confirmSpan()
      } else if (e.key === 'Escape' && pending) {
        e.preventDefault()
        cancelSpan()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [readOnly, pending, confirmSpan, cancelSpan])

  const renderUtteranceText = (u: Utterance, paragraphId: string) => {
    const spans = (spansByParagraph.get(paragraphId) ?? [])
      .slice()
      .sort((a, b) => a.value.start - b.value.start)
    const ref = (el: HTMLPreElement | null) => {
      if (el) textRefs.current.set(paragraphId, el)
      else textRefs.current.delete(paragraphId)
    }
    if (spans.length === 0) {
      return (
        <pre ref={ref} style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
          {u.text}
        </pre>
      )
    }
    const parts: Array<{
      kind: 'text' | 'span'
      key: string
      value: string
      label?: string
      color?: string
    }> = []
    let cursor = 0
    spans.forEach((s, i) => {
      if (s.value.start > cursor)
        parts.push({ kind: 'text', key: `t-${i}`, value: u.text.slice(cursor, s.value.start) })
      const labelIdx = labels.indexOf(s.label ?? '')
      parts.push({
        kind: 'span',
        key: s.id,
        value: u.text.slice(s.value.start, s.value.end),
        label: s.label,
        color: labelColor(Math.max(0, labelIdx)),
      })
      cursor = s.value.end
    })
    if (cursor < u.text.length)
      parts.push({ kind: 'text', key: 't-tail', value: u.text.slice(cursor) })
    return (
      <pre ref={ref} style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
        {parts.map((p) =>
          p.kind === 'text' ? (
            <span key={p.key}>{p.value}</span>
          ) : (
            <span
              key={p.key}
              style={{
                background: `${p.color}30`,
                borderBottom: `2px solid ${p.color}`,
                padding: '0 2px',
              }}
              title={p.label}
            >
              {p.value}
            </span>
          ),
        )}
      </pre>
    )
  }

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {!readOnly && (
        <LabelPalette labels={labels} activeLabel={activeLabel} onChange={setActiveLabel} />
      )}
      {utterances.map((u, i) => {
        const paragraphId = String(i)
        return (
          <Card
            key={paragraphId}
            size="small"
            title={
              <Tag color={u.author === 'human' || u.author === 'user' ? 'blue' : 'green'}>
                {u.author || `消息 ${i + 1}`}
              </Tag>
            }
            onMouseUp={readOnly ? undefined : () => captureSelection(paragraphId)}
            style={pending?.paragraphId === paragraphId ? { borderColor: '#1890FF' } : undefined}
          >
            {renderUtteranceText(u, paragraphId)}
          </Card>
        )
      })}

      {pending && !readOnly && (
        <div
          style={{
            padding: 8,
            background: 'var(--ant-color-bg-layout)',
            borderRadius: 6,
            display: 'flex',
            gap: 8,
            alignItems: 'center',
          }}
        >
          <Typography.Text>
            选中文本:<Tag color="blue">{pending.text}</Tag>
          </Typography.Text>
          <Typography.Text type="secondary">标签:{activeLabel ?? '(未选)'}</Typography.Text>
          <Button type="primary" icon={<CheckOutlined />} onClick={confirmSpan}>
            确认
          </Button>
          <Button icon={<CloseOutlined />} onClick={cancelSpan}>
            取消
          </Button>
        </div>
      )}

      {spansByParagraph.size > 0 && (
        <Card size="small" title={`已标注 (${[...spansByParagraph.values()].flat().length})`}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {[...spansByParagraph.values()].flat().map((s) => {
              const idx = labels.indexOf(s.label ?? '')
              return (
                <Space key={s.id} style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space>
                    <Tag color={labelColor(Math.max(0, idx))}>{s.label}</Tag>
                    <span style={{ fontSize: 12, color: 'var(--ant-color-text-secondary)' }}>
                      #{Number(s.value.paragraphId) + 1}
                    </span>
                    <span>{s.value.text}</span>
                  </Space>
                  {!readOnly && (
                    <Button type="text" size="small" onClick={() => onDeleteRegion(s.id)}>
                      删除
                    </Button>
                  )}
                </Space>
              )
            })}
          </Space>
        </Card>
      )}
    </Space>
  )
}
