import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Input, Space, Tag, Typography } from 'antd'
import type { InputRef } from 'antd'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import type { Region, ImageDimensions } from '../hooks/useAnnotationRegions'
import { regionBoundingBox } from '../utils/regions'
import RegionCropPreview from './RegionCropPreview'

/** 匹配 hotkey 字符串（如 "ctrl+1"、"shift+a"）与键盘事件 */
function matchHotkey(e: KeyboardEvent, hotkey: string): boolean {
  const parts = hotkey
    .toLowerCase()
    .split('+')
    .map((p) => p.trim())
  const key = parts[parts.length - 1]
  const needCtrl = parts.includes('ctrl') || parts.includes('control')
  const needShift = parts.includes('shift')
  const needAlt = parts.includes('alt') || parts.includes('option')
  const needMeta = parts.includes('meta') || parts.includes('cmd') || parts.includes('command')
  return (
    e.key.toLowerCase() === key &&
    e.ctrlKey === needCtrl &&
    e.shiftKey === needShift &&
    e.altKey === needAlt &&
    e.metaKey === needMeta
  )
}

interface TextAreaAnnotatorProps {
  task: AnnotationTask
  labels: string[]
  objectConfig?: LabelStudioObjectConfig
  controlConfig?: LabelStudioControlConfig
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
  readOnly?: boolean
  // perRegion 支持
  perRegion?: boolean
  selectedRegionId?: string | null
  /** 当前选中区域的已有文本（回显用） */
  currentRegionText?: string | null
  /** perRegion 结果通过回调通知父组件，不通过 onSubmit */
  onPerRegionResult?: (regionId: string, result: AnnotationResultItem | null) => void
  /** Selected region for crop preview */
  selectedRegion?: Region | null
  imageDimensions?: ImageDimensions | null
  imageUrl?: string
}

export default function TextAreaAnnotator({
  task,
  objectConfig,
  controlConfig,
  onSubmit,
  submitting,
  readOnly = false,
  perRegion = false,
  selectedRegionId,
  currentRegionText,
  onPerRegionResult,
  selectedRegion,
  imageDimensions,
  imageUrl,
}: TextAreaAnnotatorProps) {
  const [value, setValue] = useState('')
  const [submissionCount, setSubmissionCount] = useState(0)
  const inputRef = useRef<InputRef>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const objectValue = objectConfig
    ? (task.data?.[objectConfig.field] as string | undefined)
    : undefined

  // Read control attrs
  const rows = Number(controlConfig?.attrs?.rows) || 4
  const maxSubmissions = controlConfig?.maxUsages
  const editable = controlConfig?.attrs?.editable !== 'false'
  const placeholder =
    controlConfig?.attrs?.placeholder || controlConfig?.name
      ? `请输入 ${controlConfig.name} 标注内容`
      : '请输入标注内容'
  const shortcuts = useMemo(() => controlConfig?.shortcuts ?? [], [controlConfig?.shortcuts])

  // Reset on task change
  useEffect(() => {
    setValue('')
    setSubmissionCount(0)
  }, [task.id])

  // 当选中区域变化时，回显已有文本
  useEffect(() => {
    if (
      perRegion &&
      selectedRegionId &&
      currentRegionText !== undefined &&
      currentRegionText !== null
    ) {
      setValue(currentRegionText)
    } else if (perRegion && !selectedRegionId) {
      setValue('')
    }
  }, [perRegion, selectedRegionId, currentRegionText])

  const buildResult = useCallback(
    (text: string): AnnotationResultItem => ({
      from_name: controlConfig?.name || 'answer',
      to_name: controlConfig?.toName || objectConfig?.name || 'text',
      type: 'textarea',
      value: { text: [text] },
    }),
    [controlConfig?.name, controlConfig?.toName, objectConfig?.name],
  )

  /** 把 Shortcut 文本插入到光标位置（无光标则追加到末尾） */
  const insertText = useCallback(
    (text: string) => {
      const textarea =
        (
          inputRef.current as {
            resizableTextArea?: { textArea?: HTMLTextAreaElement }
          } | null
        )?.resizableTextArea?.textArea ?? null
      if (!textarea) {
        setValue((v) => v + text)
        return
      }
      const start = textarea.selectionStart ?? value.length
      const end = textarea.selectionEnd ?? value.length
      const next = value.slice(0, start) + text + value.slice(end)
      setValue(next)
      requestAnimationFrame(() => {
        textarea.focus()
        const pos = start + text.length
        textarea.setSelectionRange(pos, pos)
      })
    },
    [value],
  )

  // perRegion 模式：自动保存文本到选中区域（防抖 500ms）
  useEffect(() => {
    if (!perRegion || !selectedRegionId || !onPerRegionResult) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      if (value.trim()) {
        onPerRegionResult(selectedRegionId, buildResult(value))
      } else {
        onPerRegionResult(selectedRegionId, null)
      }
    }, 500)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [perRegion, selectedRegionId, onPerRegionResult, value, buildResult])

  // Shortcut 全局快捷键监听（ctrl/shift/alt/meta 组合不会干扰文本输入）
  useEffect(() => {
    if (readOnly || shortcuts.length === 0) return
    const handler = (e: KeyboardEvent) => {
      for (const sc of shortcuts) {
        if (sc.hotkey && matchHotkey(e, sc.hotkey)) {
          e.preventDefault()
          insertText(sc.value)
          return
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [readOnly, shortcuts, insertText])

  const handleGlobalSubmit = () => {
    onSubmit([buildResult(value)])
    setSubmissionCount((c) => c + 1)
  }

  // perRegion 模式下，无选中区域时显示提示
  if (perRegion && !selectedRegionId) {
    return (
      <Card size="small" style={{ opacity: 0.5 }}>
        <Typography.Text type="secondary">请先在画布上选中一个标注区域</Typography.Text>
      </Card>
    )
  }

  const showCrop = perRegion && selectedRegion && imageDimensions && imageUrl

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {/* Per-region crop preview */}
      {showCrop ? (
        <RegionCropPreview
          imageUrl={imageUrl}
          bbox={selectedRegion ? regionBoundingBox(selectedRegion) : null}
          imageWidth={imageDimensions.width}
          imageHeight={imageDimensions.height}
          height={120}
        />
      ) : objectConfig?.tag === 'Image' && objectValue ? (
        <img
          src={objectValue}
          alt="data"
          style={{ maxWidth: '100%', maxHeight: 160, borderRadius: 6 }}
        />
      ) : (
        <Card size="small">
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
            {objectValue || '无内容'}
          </Typography.Paragraph>
        </Card>
      )}

      {shortcuts.length > 0 && (
        <Space wrap size={[4, 4]}>
          {shortcuts.map((sc, i) => (
            <Tag
              key={i}
              color={sc.background || 'blue'}
              style={{ cursor: readOnly ? 'default' : 'pointer', userSelect: 'none' }}
              onClick={() => !readOnly && insertText(sc.value)}
            >
              {sc.alias || sc.value}
              {sc.hotkey ? ` (${sc.hotkey})` : ''}
            </Tag>
          ))}
        </Space>
      )}

      <Input.TextArea
        ref={inputRef}
        value={value}
        onChange={(event) => setValue(event.target.value)}
        rows={rows}
        placeholder={placeholder}
        disabled={readOnly || !editable}
        style={{ resize: 'vertical' }}
      />
      {!readOnly && !perRegion && (
        <Space>
          <Button
            type="primary"
            onClick={handleGlobalSubmit}
            loading={submitting}
            disabled={
              !value.trim() || (maxSubmissions !== undefined && submissionCount >= maxSubmissions)
            }
          >
            提交
          </Button>
          {maxSubmissions !== undefined && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {submissionCount} / {maxSubmissions}
            </Typography.Text>
          )}
        </Space>
      )}
    </Space>
  )
}
