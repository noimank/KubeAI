import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Card, Input, Space, Typography } from 'antd'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import type { AnnotationRegion, ImageDimensions } from '../hooks/useAnnotationRegions'
import RegionCropPreview from './RegionCropPreview'
import { appendAuthToken } from '@/utils/constants'

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
  selectedRegion?: AnnotationRegion | null
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
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const objectValue = objectConfig
    ? (task.data?.[objectConfig.field] as string | undefined)
    : undefined

  // Reset on task change
  useEffect(() => {
    setValue('')
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

  const handleGlobalSubmit = () => {
    onSubmit([buildResult(value)])
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
          spatial={selectedRegion.spatial}
          imageWidth={imageDimensions.width}
          imageHeight={imageDimensions.height}
          height={120}
        />
      ) : objectConfig?.tag === 'Image' && objectValue ? (
        <img
          src={appendAuthToken(objectValue)}
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

      <Input.TextArea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        rows={4}
        placeholder={
          controlConfig?.name ? `请输入 ${controlConfig.name} 标注内容` : '请输入标注内容'
        }
        disabled={readOnly}
        style={{ resize: 'vertical' }}
      />
      {!readOnly && !perRegion && (
        <Button
          type="primary"
          onClick={handleGlobalSubmit}
          loading={submitting}
          disabled={!value.trim()}
        >
          提交
        </Button>
      )}
    </Space>
  )
}
