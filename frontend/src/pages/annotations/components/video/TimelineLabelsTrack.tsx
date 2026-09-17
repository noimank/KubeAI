import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { List, Space, Tag, Typography } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import { getMessageInstance } from '@/utils/messageHolder'
import { labelColor } from '../annotationColors'
import LabelPalette from '../LabelPalette'
import { regionsOf } from '../../utils/regions'
import type { Region } from '../../hooks/useAnnotationRegions'
import type { LabelStudioControlConfig } from '../../utils/parseLabelConfig'
import { useVideoPlayerContext } from './VideoPlayerContext'
import { generateId } from '../../utils/id'

interface TimelineLabelsTrackProps {
  controlConfig: LabelStudioControlConfig
  regions: Region[]
  selectedRegionId: string | null
  readOnly: boolean
  onAddRegion: (region: Region) => void
  onDeleteRegion: (id: string) => void
  onSelectRegion: (id: string | null) => void
}

/**
 * TimelineLabels 范围轨道 —— 在时间轴上拖拽创建帧区间（start/end 1-based inclusive）。
 * 自带 label（controlConfig.choices）。点击范围选中，列表可删除。MVP：创建+选中+删除
 *（调整用删除重建）；增强：边缘调整/整体平移、多段 ranges。
 */
export default function TimelineLabelsTrack({
  controlConfig,
  regions,
  selectedRegionId,
  readOnly,
  onAddRegion,
  onDeleteRegion,
  onSelectRegion,
}: TimelineLabelsTrackProps) {
  const player = useVideoPlayerContext()
  const { framesCount, seekToFrame } = player
  const labels = useMemo(() => controlConfig.choices.map((c) => c.value), [controlConfig.choices])
  const [activeLabel, setActiveLabel] = useState<string | null>(labels[0] ?? null)
  const trackRef = useRef<HTMLDivElement>(null)
  const [drag, setDrag] = useState<{ start: number; end: number } | null>(null)

  useEffect(() => {
    setActiveLabel(labels[0] ?? null)
    setDrag(null)
  }, [labels])

  const tlRegions = useMemo(
    () => regionsOf(regions, controlConfig.name, 'timelinelabels'),
    [regions, controlConfig.name],
  )

  const frameAt = useCallback(
    (clientX: number): number => {
      const rect = trackRef.current?.getBoundingClientRect()
      if (!rect || framesCount <= 0) return 1
      return Math.max(
        1,
        Math.min(framesCount, Math.round(((clientX - rect.left) / rect.width) * framesCount)),
      )
    },
    [framesCount],
  )

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (readOnly) return
      const f = frameAt(e.clientX)
      setDrag({ start: f, end: f })
    },
    [readOnly, frameAt],
  )

  useEffect(() => {
    if (!drag) return
    const onMove = (e: MouseEvent) => setDrag((d) => (d ? { ...d, end: frameAt(e.clientX) } : null))
    const onUp = () => {
      setDrag((d) => {
        if (d) {
          if (labels.length > 0 && !activeLabel) {
            getMessageInstance()?.warning('请先选择标签')
            return null
          }
          const start = Math.min(d.start, d.end)
          const end = Math.max(d.start, d.end)
          onAddRegion({
            id: generateId(),
            fromName: controlConfig.name,
            label: activeLabel ?? undefined,
            value: { kind: 'timelinelabels', ranges: [{ start, end }] },
            perRegionResults: {},
          })
        }
        return null
      })
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [drag, frameAt, labels.length, activeLabel, controlConfig.name, onAddRegion])

  const dragPct =
    drag && framesCount > 0
      ? {
          left: (Math.min(drag.start, drag.end) / framesCount) * 100,
          width: (Math.abs(drag.end - drag.start) / framesCount) * 100,
        }
      : null

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      {!readOnly && labels.length > 0 && (
        <LabelPalette labels={labels} activeLabel={activeLabel} onChange={setActiveLabel} />
      )}
      <div
        ref={trackRef}
        onMouseDown={onMouseDown}
        style={{
          position: 'relative',
          height: 28,
          background: 'var(--ant-color-fill-quaternary)',
          borderRadius: 4,
          cursor: readOnly ? 'default' : 'crosshair',
        }}
      >
        {tlRegions.map((region, i) => {
          const range = region.value.ranges[0]
          if (!range || framesCount <= 0) return null
          const left = (range.start / framesCount) * 100
          const width = (Math.max(0, range.end - range.start) / framesCount) * 100
          const isSelected = region.id === selectedRegionId
          return (
            <div
              key={region.id}
              onMouseDown={(e) => e.stopPropagation()}
              onClick={() => onSelectRegion(isSelected ? null : region.id)}
              title={`${region.label ?? ''}: 帧 ${range.start}-${range.end}`}
              style={{
                position: 'absolute',
                left: `${left}%`,
                width: `${Math.max(0.5, width)}%`,
                top: 2,
                bottom: 2,
                background: labelColor(i),
                opacity: isSelected ? 0.9 : 0.6,
                borderRadius: 3,
                cursor: 'pointer',
                border: isSelected ? '2px solid #fff' : 'none',
                boxSizing: 'border-box',
              }}
            />
          )
        })}
        {dragPct && (
          <div
            style={{
              position: 'absolute',
              left: `${dragPct.left}%`,
              width: `${Math.max(0.5, dragPct.width)}%`,
              top: 2,
              bottom: 2,
              background: '#1890ff',
              opacity: 0.4,
              borderRadius: 3,
              pointerEvents: 'none',
            }}
          />
        )}
      </div>
      {tlRegions.length > 0 && (
        <List
          size="small"
          dataSource={tlRegions}
          renderItem={(region, i) => {
            const range = region.value.ranges[0]
            return (
              <List.Item
                style={{
                  padding: '4px 12px',
                  cursor: 'pointer',
                  background:
                    selectedRegionId === region.id ? 'var(--ant-color-primary-bg)' : undefined,
                }}
                onClick={() => {
                  onSelectRegion(region.id)
                  if (range) seekToFrame(range.start)
                }}
              >
                <Space>
                  <Tag color={labelColor(i)}>{region.label || `区间 ${i + 1}`}</Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    帧 {range?.start}-{range?.end}
                  </Typography.Text>
                </Space>
                {!readOnly && (
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      onDeleteRegion(region.id)
                    }}
                    style={{
                      border: 'none',
                      background: 'transparent',
                      cursor: 'pointer',
                      color: 'var(--ant-color-danger)',
                    }}
                  >
                    <DeleteOutlined />
                  </button>
                )}
              </List.Item>
            )
          }}
        />
      )}
    </div>
  )
}
