import { useEffect, useRef, useState } from 'react'
import { Button, Space, Spin, Typography } from 'antd'
import { PauseCircleOutlined, PlayCircleOutlined } from '@ant-design/icons'
import WaveSurfer from 'wavesurfer.js'

/** Audio 对象查看器 —— wavesurfer 波形播放器（仅播放） */
export default function AudioViewer({ value, height = 80 }: { value: unknown; height?: number }) {
  const url = typeof value === 'string' ? value : ''
  const ref = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WaveSurfer | null>(null)
  const [ready, setReady] = useState(false)
  const [playing, setPlaying] = useState(false)

  useEffect(() => {
    if (!ref.current || !url) return
    const ws = WaveSurfer.create({
      url,
      container: ref.current,
      height,
      waveColor: 'var(--ant-color-border, #d9d9d9)',
      progressColor: '#1677ff',
      cursorColor: '#1677ff',
      normalize: true,
    })
    wsRef.current = ws
    ws.on('ready', () => setReady(true))
    ws.on('play', () => setPlaying(true))
    ws.on('pause', () => setPlaying(false))
    ws.on('finish', () => setPlaying(false))
    return () => {
      ws.destroy()
      wsRef.current = null
      setReady(false)
      setPlaying(false)
    }
  }, [url, height])

  if (!url) return <Typography.Text type="secondary">无音频数据</Typography.Text>

  return (
    <div style={{ marginBottom: 16 }}>
      <Space style={{ marginBottom: 8 }}>
        <Button
          size="small"
          icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
          disabled={!ready}
          onClick={() => wsRef.current?.playPause()}
        >
          {playing ? '暂停' : '播放'}
        </Button>
        {!ready && <Spin size="small" />}
      </Space>
      <div ref={ref} />
    </div>
  )
}
