import { useCallback, useEffect, useRef, useState } from 'react'
import { Button, Card, InputNumber, Rate, Space, TreeSelect, Typography } from 'antd'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import type { AnnotationRegion, ImageDimensions } from '../hooks/useAnnotationRegions'
import RegionCropPreview from './RegionCropPreview'
import { appendAuthToken } from '@/utils/constants'
import {
  type LabelStudioControlConfig,
  type LabelStudioObjectConfig,
  taxonomyToTreeData,
} from '../utils/parseLabelConfig'

interface FormControlAnnotatorProps {
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
  /** 当前选中区域的已有值 */
  currentRegionValue?: Record<string, unknown> | null
  /** perRegion 结果通过回调通知父组件 */
  onPerRegionResult?: (regionId: string, result: AnnotationResultItem | null) => void
  /** Selected region for crop preview */
  selectedRegion?: AnnotationRegion | null
  imageDimensions?: ImageDimensions | null
  imageUrl?: string
}

export default function FormControlAnnotator({
  task,
  labels,
  objectConfig,
  controlConfig,
  onSubmit,
  submitting,
  readOnly = false,
  perRegion = false,
  selectedRegionId,
  currentRegionValue,
  onPerRegionResult,
  selectedRegion,
  imageDimensions,
  imageUrl,
}: FormControlAnnotatorProps) {
  const type = controlConfig?.type
  const field = objectConfig?.field || ''
  const value = field ? (task.data?.[field] as string | undefined) : undefined

  const [rating, setRating] = useState<number>(0)
  const [number, setNumber] = useState<number | null>(null)
  const [taxonomyPath, setTaxonomyPath] = useState<string[]>([])

  // Reset on task change
  useEffect(() => {
    setRating(0)
    setNumber(null)
    setTaxonomyPath([])
  }, [task.id])

  // 当选中区域变化时，回显已有值
  useEffect(() => {
    if (!perRegion || !selectedRegionId || !currentRegionValue) {
      if (perRegion && !selectedRegionId) {
        setRating(0)
        setNumber(null)
        setTaxonomyPath([])
      }
      return
    }
    if (type === 'rating' && typeof currentRegionValue.rating === 'number') {
      setRating(currentRegionValue.rating)
    } else if (type === 'number' && typeof currentRegionValue.number === 'number') {
      setNumber(currentRegionValue.number)
    } else if (type === 'taxonomy') {
      const cv = currentRegionValue as Record<string, unknown>
      const taxArr = cv.taxonomy as unknown[][] | undefined
      if (Array.isArray(taxArr?.[0])) {
        setTaxonomyPath(taxArr![0] as string[])
      }
    }
  }, [perRegion, selectedRegionId, currentRegionValue, type])

  const buildResult = useCallback((): AnnotationResultItem | null => {
    const name = controlConfig?.name || type || 'control'
    const toName = controlConfig?.toName || objectConfig?.name || 'data'
    if (type === 'rating') {
      if (rating <= 0) return null
      return { from_name: name, to_name: toName, type: 'rating', value: { rating } }
    }
    if (type === 'number') {
      if (number === null) return null
      return { from_name: name, to_name: toName, type: 'number', value: { number } }
    }
    if (type === 'taxonomy') {
      if (taxonomyPath.length === 0) return null
      return {
        from_name: name,
        to_name: toName,
        type: 'taxonomy',
        value: { taxonomy: [taxonomyPath] },
      }
    }
    return null
  }, [type, rating, number, taxonomyPath, controlConfig, objectConfig])

  // perRegion 模式：值变更时自动保存
  const buildAndPersist = useCallback(
    (result: AnnotationResultItem | null) => {
      if (perRegion && selectedRegionId && onPerRegionResult) {
        onPerRegionResult(selectedRegionId, result)
      }
    },
    [perRegion, selectedRegionId, onPerRegionResult],
  )

  const handleGlobalSubmit = () => {
    const result = buildResult()
    if (!result) return
    onSubmit([result])
  }

  // perRegion mode: auto-save on value change via effect
  const prevResultRef = useRef<AnnotationResultItem | null>(null)
  useEffect(() => {
    if (!perRegion || !selectedRegionId) return
    const result = buildResult()
    // Only persist if result actually changed
    if (JSON.stringify(result) !== JSON.stringify(prevResultRef.current)) {
      prevResultRef.current = result
      buildAndPersist(result)
    }
  }, [perRegion, selectedRegionId, rating, number, taxonomyPath, buildResult, buildAndPersist])

  // perRegion 模式下，无选中区域时显示提示
  if (perRegion && !selectedRegionId) {
    return (
      <Card size="small" style={{ opacity: 0.5 }}>
        <Typography.Text type="secondary">请先在画布上选中一个标注区域</Typography.Text>
      </Card>
    )
  }

  const showCrop = perRegion && selectedRegion && imageDimensions && imageUrl

  const renderObjectPreview = () => {
    if (showCrop) {
      return (
        <RegionCropPreview
          imageUrl={imageUrl}
          spatial={selectedRegion!.spatial}
          imageWidth={imageDimensions!.width}
          imageHeight={imageDimensions!.height}
          height={100}
        />
      )
    }
    if (!value) return null
    if (objectConfig?.tag === 'Image')
      return (
        <img
          src={appendAuthToken(value)}
          style={{ maxWidth: '100%', maxHeight: 160, borderRadius: 6 }}
          alt="data"
        />
      )
    if (objectConfig?.tag === 'Audio')
      return <audio src={appendAuthToken(value)} controls style={{ width: '100%' }} />
    if (objectConfig?.tag === 'Video')
      return <video src={appendAuthToken(value)} controls style={{ width: '100%' }} />
    if (objectConfig?.tag === 'Text' || objectConfig?.tag === 'HyperText')
      return (
        <Card size="small">
          <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
            {value}
          </Typography.Paragraph>
        </Card>
      )
    return null
  }

  const renderInput = () => {
    if (type === 'rating') {
      return (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Typography.Text>评分(0-10)</Typography.Text>
          <Rate
            count={10}
            value={rating}
            onChange={readOnly ? undefined : setRating}
            disabled={readOnly}
            allowHalf
          />
          {rating > 0 && <Typography.Text type="secondary">当前:{rating} / 10</Typography.Text>}
        </Space>
      )
    }
    if (type === 'number') {
      return (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Typography.Text>数值</Typography.Text>
          <InputNumber
            value={number ?? undefined}
            onChange={(v) => setNumber(v ?? null)}
            disabled={readOnly}
            style={{ width: '100%' }}
            placeholder="请输入数值"
          />
        </Space>
      )
    }
    if (type === 'taxonomy') {
      const tree = taxonomyToTreeData(controlConfig?.taxonomy)
      return (
        <Space direction="vertical" size="small" style={{ width: '100%' }}>
          <Typography.Text>分类</Typography.Text>
          <TreeSelect
            treeData={tree}
            value={taxonomyPath}
            onChange={readOnly ? undefined : (v) => setTaxonomyPath((v as string[]) ?? [])}
            treeCheckable
            showCheckedStrategy="SHOW_CHILD"
            disabled={readOnly}
            placeholder="选择分类路径"
            style={{ width: '100%' }}
            treeDefaultExpandAll
          />
        </Space>
      )
    }
    return (
      <Typography.Text type="secondary">
        当前控件类型 ({type ?? 'unknown'}) 暂未实现
      </Typography.Text>
    )
  }

  // labels 字段未使用，保留兼容
  void labels

  const globalResult = buildResult()
  const canSubmit = !readOnly && !perRegion && globalResult !== null

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {renderObjectPreview()}
      <Card size="small">{renderInput()}</Card>
      {!readOnly && !perRegion && (
        <Button
          type="primary"
          onClick={handleGlobalSubmit}
          loading={submitting}
          disabled={!canSubmit}
        >
          提交
        </Button>
      )}
    </Space>
  )
}
