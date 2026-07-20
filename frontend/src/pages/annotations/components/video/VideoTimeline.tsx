import type { ReactNode } from 'react'
import { Button, Select, Space, Tooltip, Typography } from 'antd'
import {
  SyncOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  StepBackwardOutlined,
  StepForwardOutlined,
} from '@ant-design/icons'
import { useVideoPlayerContext } from './VideoPlayerContext'

/** 视频时间轴：传输控制 + 帧刻度轴 + 播放头。点击刻度轴 seek。 */
export default function VideoTimeline({ children }: { children?: ReactNode }) {
  const player = useVideoPlayerContext()
  const {
    currentFrame,
    framesCount,
    playing,
    togglePlay,
    seekToFrame,
    framerate,
    duration,
    ready,
  } = player
  const { speed, setSpeed, loop, toggleLoop } = player
  const pct = framesCount > 0 ? (currentFrame / framesCount) * 100 : 0
  const ticks =
    framesCount > 0 ? Array.from({ length: 11 }, (_, i) => Math.round((i / 10) * framesCount)) : []

  const speedOptions = [
    { value: 0.25, label: '0.25x' },
    { value: 0.5, label: '0.5x' },
    { value: 0.75, label: '0.75x' },
    { value: 1, label: '1x' },
    { value: 1.25, label: '1.25x' },
    { value: 1.5, label: '1.5x' },
    { value: 2, label: '2x' },
  ]

  const onAxisClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (framesCount <= 0) return
    const rect = e.currentTarget.getBoundingClientRect()
    const frame = Math.round(((e.clientX - rect.left) / rect.width) * framesCount)
    seekToFrame(frame)
  }

  return (
    <div
      style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '8px 0', flexShrink: 0 }}
    >
      <Space wrap>
        <Button
          size="small"
          icon={<StepBackwardOutlined />}
          disabled={!ready}
          onClick={() => seekToFrame(currentFrame - 1)}
        />
        <Button
          size="small"
          icon={playing ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
          disabled={!ready}
          onClick={togglePlay}
        >
          {playing ? '暂停' : '播放'}
        </Button>
        <Button
          size="small"
          icon={<StepForwardOutlined />}
          disabled={!ready}
          onClick={() => seekToFrame(currentFrame + 1)}
        />
        <Select
          size="small"
          value={speed}
          onChange={(v) => setSpeed(v)}
          style={{ width: 72 }}
          options={speedOptions}
        />
        <Tooltip title={loop ? '已开启循环' : '循环播放'}>
          <Button
            size="small"
            type={loop ? 'primary' : 'default'}
            icon={<SyncOutlined />}
            onClick={toggleLoop}
          />
        </Tooltip>
        <Typography.Text>
          帧 {currentFrame} / {framesCount}
        </Typography.Text>
        <Typography.Text type="secondary">
          {framerate} fps · {duration.toFixed(1)}s
        </Typography.Text>
      </Space>
      <div
        onClick={onAxisClick}
        style={{
          position: 'relative',
          height: 24,
          background: 'var(--ant-color-fill-tertiary)',
          borderRadius: 4,
          cursor: ready ? 'pointer' : 'default',
        }}
      >
        {ticks.map((f, i) => (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: `${(f / Math.max(framesCount, 1)) * 100}%`,
              top: 0,
              height: 6,
              width: 1,
              background: 'var(--ant-color-border)',
            }}
          >
            <span
              style={{
                position: 'absolute',
                top: 8,
                left: 2,
                fontSize: 10,
                color: 'var(--ant-color-text-secondary)',
                whiteSpace: 'nowrap',
              }}
            >
              {f}
            </span>
          </div>
        ))}
        {/* 播放头 */}
        <div
          style={{
            position: 'absolute',
            left: `${pct}%`,
            top: 0,
            bottom: 0,
            width: 2,
            background: '#1677ff',
            pointerEvents: 'none',
          }}
        />
      </div>
      {children}
    </div>
  )
}
