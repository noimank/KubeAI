import { Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { getSelectableImages } from '@/services/images'
import type { ImageCategory, ImageSelectable } from '@/types/image'

interface ImageSelectProps {
  value?: string | null
  onChange?: (imageId: string | null) => void
  placeholder?: string
  disabled?: boolean
  style?: React.CSSProperties
  /** 仅展示该类别的镜像 (训练表单传 'training', 推理表单传 'inference') */
  category?: ImageCategory
}

function groupBySource(images: ImageSelectable[]) {
  const preset: ImageSelectable[] = []
  const custom: ImageSelectable[] = []
  for (const img of images) {
    if (img.source === 'preset') {
      preset.push(img)
    } else {
      custom.push(img)
    }
  }
  return { preset, custom }
}

export default function ImageSelect({
  value,
  onChange,
  placeholder = '请选择镜像',
  disabled,
  style,
  category,
}: ImageSelectProps) {
  const { data: images = [], isLoading } = useQuery({
    queryKey: ['selectableImages', category ?? 'all'],
    queryFn: () => getSelectableImages(category),
  })

  const { preset, custom } = groupBySource(images)
  const hasData = images.length > 0

  return (
    <Select
      value={value ?? undefined}
      onChange={(val) => onChange?.(val ?? null)}
      placeholder={placeholder}
      disabled={disabled}
      loading={isLoading}
      style={{ width: '100%', ...style }}
      allowClear
      notFoundContent={!isLoading && !hasData ? '暂无可用镜像' : undefined}
    >
      {preset.length > 0 && (
        <Select.OptGroup label="预置镜像">
          {preset.map((img) => (
            <Select.Option key={img.id} value={img.id}>
              {img.name}:{img.tag}
            </Select.Option>
          ))}
        </Select.OptGroup>
      )}
      {custom.length > 0 && (
        <Select.OptGroup label="自定义镜像">
          {custom.map((img) => (
            <Select.Option key={img.id} value={img.id}>
              {img.name}:{img.tag}
            </Select.Option>
          ))}
        </Select.OptGroup>
      )}
    </Select>
  )
}
