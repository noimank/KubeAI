import { useEffect, useRef } from 'react'
import { Tag } from 'antd'
import { labelColor } from './annotationColors'

interface LabelPaletteProps {
  labels: string[]
  activeLabel: string | null
  onChange: (label: string) => void
  /** 是否监听数字键 1-9 选择标签,默认开启 */
  enableHotkeys?: boolean
}

/**
 * 标签选择板:点击或数字键 1-9 选中当前激活标签。
 * 供目标检测 / 分割 / 关键点等图形标注组件复用。
 */
export default function LabelPalette({
  labels,
  activeLabel,
  onChange,
  enableHotkeys = true,
}: LabelPaletteProps) {
  const labelsRef = useRef(labels)
  labelsRef.current = labels

  useEffect(() => {
    if (!enableHotkeys) return
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.ctrlKey || e.metaKey || e.altKey) return
      const num = Number(e.key)
      if (!Number.isInteger(num) || num < 1 || num > 9) return
      const label = labelsRef.current[num - 1]
      if (label) {
        e.preventDefault()
        onChange(label)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onChange, enableHotkeys])

  if (labels.length === 0) return null

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
      {labels.map((label, index) => {
        const active = label === activeLabel
        const color = labelColor(index)
        return (
          <Tag
            key={label}
            color={active ? color : undefined}
            style={{
              cursor: 'pointer',
              padding: '2px 8px',
              borderColor: color,
              userSelect: 'none',
            }}
            onClick={() => onChange(label)}
          >
            {index < 9 && (
              <span style={{ opacity: 0.65, marginRight: 4, fontFamily: 'monospace' }}>
                {index + 1}
              </span>
            )}
            {label}
          </Tag>
        )
      })}
    </div>
  )
}
