import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Space, Tag, Typography } from 'antd'
import { CheckOutlined, CloseOutlined } from '@ant-design/icons'
import LabelPalette from './LabelPalette'
import { labelColor } from './annotationColors'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'
import { regionsOf } from '../utils/regions'
import { generateId } from '../utils/id'

// ── Component ───────────────────────────────────────────────────────────────

export default function NerTextAnnotator({
  task,
  objectConfig,
  controlConfig,
  readOnly = false,
  regions,
  onAddRegion,
  onDeleteRegion,
}: SpatialAnnotatorProps) {
  const field = objectConfig?.field || 'text'
  const text = (task.data?.[field] as string | undefined) ?? ''
  const labels = useMemo(() => controlConfig.choices.map((c) => c.value), [controlConfig.choices])
  const [activeLabel, setActiveLabel] = useState<string | null>(labels[0] ?? null)
  const [pendingSelection, setPendingSelection] = useState<{
    start: number
    end: number
    text: string
  } | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const textRef = useRef<HTMLPreElement>(null)

  // Filter text-span regions from this control (covers Labels + HyperTextLabels)
  const spanRegions = regionsOf(regions, controlConfig.name, 'textspan')

  useEffect(() => {
    setPendingSelection(null)
    setActiveLabel(labels[0] ?? null)
  }, [task.id, labels])

  const captureSelection = useCallback(() => {
    const sel = window.getSelection()
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) {
      setPendingSelection(null)
      return
    }
    const range = sel.getRangeAt(0)
    const textNode = textRef.current
    if (
      !textNode ||
      !textNode.contains(range.startContainer) ||
      !textNode.contains(range.endContainer)
    ) {
      setPendingSelection(null)
      return
    }
    const pre = document.createRange()
    pre.selectNodeContents(textNode)
    pre.setEnd(range.startContainer, range.startOffset)
    const start = pre.toString().length
    const selectedText = sel.toString()
    const end = start + selectedText.length
    if (selectedText.trim().length === 0) {
      setPendingSelection(null)
      return
    }
    setPendingSelection({ start, end, text: selectedText })
  }, [])

  const confirmSpan = useCallback(() => {
    if (!pendingSelection || !activeLabel) return
    onAddRegion({
      id: generateId(),
      fromName: controlConfig.name,
      label: activeLabel,
      value: {
        kind: 'textspan',
        start: pendingSelection.start,
        end: pendingSelection.end,
        text: pendingSelection.text,
      },
      perRegionResults: {},
    })
    setPendingSelection(null)
    window.getSelection()?.removeAllRanges()
  }, [pendingSelection, activeLabel, controlConfig.name, onAddRegion])

  const cancelSpan = useCallback(() => {
    setPendingSelection(null)
    window.getSelection()?.removeAllRanges()
  }, [])

  // Key handlers
  useEffect(() => {
    if (readOnly) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.key === 'Enter' && pendingSelection) {
        e.preventDefault()
        confirmSpan()
      } else if (e.key === 'Escape' && pendingSelection) {
        e.preventDefault()
        cancelSpan()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [readOnly, pendingSelection, confirmSpan, cancelSpan])

  // Render highlighted text with spans
  const renderHighlighted = () => {
    if (spanRegions.length === 0) {
      return (
        <pre ref={textRef} style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
          {text}
        </pre>
      )
    }
    const sorted = [...spanRegions].sort((a, b) => a.value.start - b.value.start)
    const parts: Array<{
      kind: 'text' | 'span'
      key: string
      value: string
      label?: string
      color?: string
    }> = []
    let cursor = 0
    sorted.forEach((s, i) => {
      if (s.value.start > cursor) {
        parts.push({ kind: 'text', key: `t-${i}`, value: text.slice(cursor, s.value.start) })
      }
      const labelIdx = labels.indexOf(s.label ?? '')
      parts.push({
        kind: 'span',
        key: s.id,
        value: text.slice(s.value.start, s.value.end),
        label: s.label,
        color: labelColor(Math.max(0, labelIdx)),
      })
      cursor = s.value.end
    })
    if (cursor < text.length) {
      parts.push({ kind: 'text', key: 't-tail', value: text.slice(cursor) })
    }
    return (
      <pre ref={textRef} style={{ margin: 0, whiteSpace: 'pre-wrap' }}>
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
                cursor: readOnly ? 'default' : 'pointer',
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
      {objectConfig?.tag === 'Image' && typeof task.data?.[field] === 'string' && (
        <Card size="small">
          <img
            src={task.data[field] as string}
            alt="data"
            style={{ maxWidth: '100%', maxHeight: 360 }}
          />
        </Card>
      )}
      <Card
        size="small"
        title="文本"
        ref={containerRef}
        onMouseUp={readOnly ? undefined : captureSelection}
        style={pendingSelection ? { borderColor: '#1890FF' } : undefined}
      >
        {renderHighlighted()}
      </Card>

      {pendingSelection && !readOnly && (
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
            选中文本:<Tag color="blue">{pendingSelection.text}</Tag>
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

      {spanRegions.length > 0 && (
        <Card size="small" title={`已标注 (${spanRegions.length})`}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {spanRegions.map((s) => {
              const idx = labels.indexOf(s.label ?? '')
              return (
                <Space key={s.id} style={{ width: '100%', justifyContent: 'space-between' }}>
                  <Space>
                    <Tag color={labelColor(Math.max(0, idx))}>{s.label}</Tag>
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
