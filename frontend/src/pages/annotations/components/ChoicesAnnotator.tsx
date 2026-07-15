import { useCallback, useEffect, useState } from 'react'
import { Button, Card, Checkbox, Image, Radio, Space, Typography } from 'antd'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from '../utils/parseLabelConfig'
import type { AnnotationRegion, ImageDimensions } from '../hooks/useAnnotationRegions'
import RegionCropPreview from './RegionCropPreview'
import { appendAuthToken } from '@/utils/constants'

interface ChoicesAnnotatorProps {
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
  /** 当前选中区域的已有选中值（回显用） */
  currentRegionChoices?: string[] | null
  /** perRegion 结果通过回调通知父组件 */
  onPerRegionResult?: (regionId: string, result: AnnotationResultItem | null) => void
  /** Selected region for crop preview */
  selectedRegion?: AnnotationRegion | null
  imageDimensions?: ImageDimensions | null
  imageUrl?: string
}

export default function ChoicesAnnotator({
  task,
  labels,
  objectConfig,
  controlConfig,
  onSubmit,
  submitting,
  readOnly = false,
  perRegion = false,
  selectedRegionId,
  currentRegionChoices,
  onPerRegionResult,
  selectedRegion,
  imageDimensions,
  imageUrl,
}: ChoicesAnnotatorProps) {
  const [selected, setSelected] = useState<string[]>([])
  const objectValue = objectConfig
    ? (task.data?.[objectConfig.field] as string | undefined)
    : undefined
  const multiple = controlConfig?.choice?.includes('multiple')

  // Reset on task change
  useEffect(() => {
    setSelected([])
  }, [task.id])

  // 当选中区域变化时，回显已有选择
  useEffect(() => {
    if (perRegion && selectedRegionId && currentRegionChoices !== undefined && currentRegionChoices !== null) {
      setSelected(currentRegionChoices)
    } else if (perRegion && !selectedRegionId) {
      setSelected([])
    }
  }, [perRegion, selectedRegionId, currentRegionChoices])

  const submitChoices = useCallback(
    (choices: string[]) => {
      const result: AnnotationResultItem = {
        from_name: controlConfig?.name || 'choice',
        to_name: controlConfig?.toName || objectConfig?.name || 'data',
        type: 'choices',
        value: { choices },
      }
      if (perRegion && selectedRegionId && onPerRegionResult) {
        onPerRegionResult(selectedRegionId, result)
      } else if (!perRegion) {
        onSubmit([result])
      }
    },
    [perRegion, selectedRegionId, onPerRegionResult, onSubmit, controlConfig, objectConfig],
  )

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
      ) : (
        <ObjectPreview objectConfig={objectConfig} value={objectValue} />
      )}

      {multiple ? (
        <>
          <Checkbox.Group
            value={selected}
            disabled={submitting || readOnly}
            onChange={(values) => {
              const next = values as string[]
              setSelected(next)
              if (perRegion) submitChoices(next)
            }}
          >
            <Space direction="vertical">
              {labels.map((label) => (
                <Checkbox key={label} value={label}>
                  {label}
                </Checkbox>
              ))}
            </Space>
          </Checkbox.Group>
          {!perRegion && (
            <Button
              type="primary"
              loading={submitting}
              disabled={selected.length === 0 || readOnly}
              onClick={() => submitChoices(selected)}
            >
              提交
            </Button>
          )}
        </>
      ) : (
        <Radio.Group
          value={selected[0]}
          disabled={submitting || readOnly}
          onChange={(event) => {
            const value = event.target.value
            setSelected([value])
            submitChoices([value])
          }}
        >
          <Space direction="vertical">
            {labels.map((label) => (
              <Radio key={label} value={label}>
                {label}
              </Radio>
            ))}
          </Space>
        </Radio.Group>
      )}
    </Space>
  )
}

function ObjectPreview({
  objectConfig,
  value,
}: {
  objectConfig?: LabelStudioObjectConfig
  value?: string
}) {
  if (objectConfig?.tag === 'Image' && value) {
    return (
      <div style={{ textAlign: 'center' }}>
        <Image src={appendAuthToken(value)} style={{ maxHeight: 160 }} />
      </div>
    )
  }
  if (objectConfig?.tag === 'Audio' && value)
    return <audio src={appendAuthToken(value)} controls style={{ width: '100%' }} />
  if (objectConfig?.tag === 'Video' && value)
    return <video src={appendAuthToken(value)} controls style={{ width: '100%' }} />

  return (
    <Card size="small">
      <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
        {value || '无内容'}
      </Typography.Paragraph>
    </Card>
  )
}
