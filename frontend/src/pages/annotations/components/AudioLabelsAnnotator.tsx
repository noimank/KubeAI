import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Card, Space, Tag, Typography } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import WaveSurfer from 'wavesurfer.js'
import RegionsPlugin from 'wavesurfer.js/dist/plugins/regions.js'
import { labelColor } from './annotationColors'
import LabelPalette from './LabelPalette'
import { regionsOf } from '../utils/regions'
import type { SpatialAnnotatorProps } from './SpatialAnnotatorProps'

/**
 * Audio Labels 标注器 —— 在波形上拖拽选择区间创建 audio region（声音事件检测）。
 * wavesurfer regions 插件负责交互；region 事件单向同步到区域状态用于序列化。
 */
export default function AudioLabelsAnnotator({
  task,
  objectConfig,
  controlConfig,
  readOnly = false,
  regions,
  selectedRegionId,
  onAddRegion,
  onUpdateRegion,
  onDeleteRegion,
  onSelectRegion,
}: SpatialAnnotatorProps) {
  const field = objectConfig?.field || 'audio'
  const url = (task.data?.[field] as string | undefined) ?? ''
  const labels = useMemo(() => controlConfig.choices.map((c) => c.value), [controlConfig.choices])
  const [activeLabel, setActiveLabel] = useState<string | null>(labels[0] ?? null)

  const containerRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WaveSurfer | null>(null)
  const regionsPluginRef = useRef<ReturnType<typeof RegionsPlugin.create> | null>(null)
  const activeLabelRef = useRef(activeLabel)
  activeLabelRef.current = activeLabel

  const audioRegions = useMemo(
    () => regionsOf(regions, controlConfig.name, 'audio'),
    [regions, controlConfig.name],
  )

  const colorForLabel = useCallback(
    (label: string | undefined, fallbackIdx: number) => {
      const idx = label ? labels.indexOf(label) : -1
      return `${labelColor(idx >= 0 ? idx : fallbackIdx)}55`
    },
    [labels],
  )

  useEffect(() => {
    if (!containerRef.current || !url) return
    const regionsPlugin = RegionsPlugin.create()
    regionsPluginRef.current = regionsPlugin
    const ws = WaveSurfer.create({
      url,
      container: containerRef.current,
      height: 96,
      waveColor: 'var(--ant-color-border, #d9d9d9)',
      progressColor: '#1677ff',
      cursorColor: '#1677ff',
      normalize: true,
      plugins: [regionsPlugin],
    })
    wsRef.current = ws

    if (!readOnly) {
      regionsPlugin.enableDragSelection({
        color: 'rgba(22, 119, 255, 0.25)',
      })
    }

    regionsPlugin.on('region-created', (r) => {
      const label = activeLabelRef.current ?? undefined
      r.setOptions({ color: colorForLabel(label, regions.length) })
      onAddRegion({
        id: r.id,
        fromName: controlConfig.name,
        label,
        value: { kind: 'audio', start: r.start, end: r.end },
        perRegionResults: {},
      })
    })
    regionsPlugin.on('region-updated', (r) => {
      onUpdateRegion(r.id, { value: { kind: 'audio', start: r.start, end: r.end } })
    })
    regionsPlugin.on('region-clicked', (r) => {
      r.play()
      onSelectRegion(selectedRegionId === r.id ? null : r.id)
    })

    return () => {
      ws.destroy()
      wsRef.current = null
      regionsPluginRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, readOnly])

  const handleDeleteSelected = useCallback(() => {
    if (!selectedRegionId) return
    regionsPluginRef.current
      ?.getRegions()
      .find((r) => r.id === selectedRegionId)
      ?.remove()
    onDeleteRegion(selectedRegionId)
  }, [selectedRegionId, onDeleteRegion])

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {!readOnly && (
        <LabelPalette labels={labels} activeLabel={activeLabel} onChange={setActiveLabel} />
      )}
      <div>
        <Space style={{ marginBottom: 8 }}>
          {!readOnly && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              在波形上拖拽选择区间创建标注，点击区间可试听。
            </Typography.Text>
          )}
        </Space>
        <div ref={containerRef} />
      </div>

      {!readOnly && (
        <Button
          icon={<DeleteOutlined />}
          disabled={!selectedRegionId}
          onClick={handleDeleteSelected}
        >
          删除选中区间
        </Button>
      )}

      {audioRegions.length > 0 && (
        <Card size="small" title={`已标注区间 (${audioRegions.length})`}>
          <Space direction="vertical" style={{ width: '100%' }}>
            {audioRegions.map((r, i) => (
              <Space key={r.id} style={{ width: '100%', justifyContent: 'space-between' }}>
                <Space>
                  <Tag
                    color={labelColor(
                      labels.indexOf(r.label ?? '') >= 0 ? labels.indexOf(r.label!) : i,
                    )}
                  >
                    {r.label || `区间 ${i + 1}`}
                  </Tag>
                  <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                    {r.value.start.toFixed(2)}s – {r.value.end.toFixed(2)}s
                  </Typography.Text>
                </Space>
                {!readOnly && (
                  <Button
                    type="text"
                    size="small"
                    danger
                    onClick={() => {
                      regionsPluginRef.current
                        ?.getRegions()
                        .find((rr) => rr.id === r.id)
                        ?.remove()
                      onDeleteRegion(r.id)
                    }}
                  >
                    删除
                  </Button>
                )}
              </Space>
            ))}
          </Space>
        </Card>
      )}
    </Space>
  )
}
