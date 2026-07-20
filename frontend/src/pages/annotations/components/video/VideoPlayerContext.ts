import { createContext, useContext } from 'react'

/**
 * 视频播放器 API —— 由 useVideoPlayer 实现，通过 Context 下发给所有子组件
 *（VideoRectangleLayer / VideoTimeline / TimelineLabelsTrack 等），共享单个 <video>。
 */
export interface VideoPlayerApi {
  /** 底层 video 元素（供 Konva.Image 作 image source） */
  videoEl: HTMLVideoElement | null
  videoWidth: number
  videoHeight: number
  /** 当前帧（1-based，round(currentTime*framerate)，钳制到 [1, framesCount]） */
  currentFrame: number
  currentTime: number
  framerate: number
  framesCount: number
  duration: number
  playing: boolean
  ready: boolean
  play: () => void
  pause: () => void
  togglePlay: () => void
  /** seek 到指定帧（1-based），落到帧中心 (frame-0.5)/framerate */
  seekToFrame: (frame: number) => void
  /** 当前播放速度倍率 */
  speed: number
  /** 设置播放速度 */
  setSpeed: (speed: number) => void
  /** 是否循环播放 */
  loop: boolean
  /** 切换循环播放 */
  toggleLoop: () => void
}

export const VideoPlayerContext = createContext<VideoPlayerApi | null>(null)

export function useVideoPlayerContext(): VideoPlayerApi {
  const ctx = useContext(VideoPlayerContext)
  if (!ctx) {
    throw new Error('useVideoPlayerContext must be used within VideoPlayerContext.Provider')
  }
  return ctx
}
