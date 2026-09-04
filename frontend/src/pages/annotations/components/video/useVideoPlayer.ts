import { useCallback, useEffect, useRef, useState } from 'react'
import type Konva from 'konva'
import type { VideoPlayerApi } from './VideoPlayerContext'

export interface VideoMeta {
  framerate: number
  framesCount: number
  duration: number
}

function clampFrame(frame: number, framesCount: number): number {
  if (framesCount <= 0) return 1
  return Math.max(1, Math.min(framesCount, Math.round(frame)))
}

/**
 * 视频播放器 hook：持有 <video> ref 与 Konva layer ref，rAF 驱动帧级重绘。
 *
 * - currentFrame = round(currentTime * framerate)，1-based，钳制 [1, framesCount]
 * - 仅当派生帧号变化才 setState（避免 60fps 的 React 渲染风暴）
 * - 播放时 rAF 循环 layer.batchDraw()（Konva.Image 拉取当前 video 帧）+ 节流 setState
 * - 暂停时监听 seeked 单次重绘
 * - seek 落到帧中心 (frame-0.5)/framerate，最大化落在正确帧
 */
export function useVideoPlayer(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  layerRef: React.RefObject<Konva.Layer | null>,
  url: string,
  framerate: number,
  onVideoMeta?: (meta: VideoMeta) => void,
  defaultSpeed = 1,
): VideoPlayerApi {
  const [ready, setReady] = useState(false)
  const [playing, setPlaying] = useState(false)
  const [currentFrame, setCurrentFrame] = useState(1)
  const [currentTime, setCurrentTime] = useState(0)
  const [videoWidth, setVideoWidth] = useState(0)
  const [videoHeight, setVideoHeight] = useState(0)
  const [duration, setDuration] = useState(0)
  const [speed, setSpeed] = useState(defaultSpeed)
  const [loop, setLoop] = useState(false)

  const framesCount =
    duration > 0 && framerate > 0 ? Math.max(1, Math.round(duration * framerate)) : 0

  const onVideoMetaRef = useRef(onVideoMeta)
  onVideoMetaRef.current = onVideoMeta

  const defaultSpeedRef = useRef(defaultSpeed)
  defaultSpeedRef.current = defaultSpeed

  const updateFrameFromVideo = useCallback(
    (force?: boolean) => {
      const video = videoRef.current
      if (!video) return
      const f = clampFrame(video.currentTime * framerate, framesCount)
      setCurrentFrame((prev) => (prev !== f || force ? f : prev))
      setCurrentTime(video.currentTime)
    },
    [videoRef, framerate, framesCount],
  )

  // 加载视频元数据
  useEffect(() => {
    const video = videoRef.current
    if (!video || !url) {
      setReady(false)
      return
    }
    setReady(false)
    const onLoaded = () => {
      setVideoWidth(video.videoWidth)
      setVideoHeight(video.videoHeight)
      setDuration(video.duration || 0)
      if (defaultSpeedRef.current !== 1) video.playbackRate = defaultSpeedRef.current
      setSpeed(defaultSpeedRef.current)
      setReady(true)
    }
    video.addEventListener('loadedmetadata', onLoaded)
    return () => video.removeEventListener('loadedmetadata', onLoaded)
  }, [videoRef, url])

  // 报告视频元数据（供序列化注入 framesCount/duration）
  useEffect(() => {
    if (ready) {
      onVideoMetaRef.current?.({ framerate, framesCount, duration })
    }
  }, [ready, framerate, framesCount, duration])

  // 渲染循环：播放时 rAF；暂停时 seeked 单次重绘
  useEffect(() => {
    const video = videoRef.current
    const layer = layerRef.current
    if (!video || !layer) return
    let raf = 0
    if (playing) {
      const loop = () => {
        layer.batchDraw()
        updateFrameFromVideo()
        raf = requestAnimationFrame(loop)
      }
      raf = requestAnimationFrame(loop)
      return () => cancelAnimationFrame(raf)
    }
    const onSeeked = () => {
      layer.batchDraw()
      updateFrameFromVideo(true)
    }
    const onPlay = () => setPlaying(true)
    const onPause = () => setPlaying(false)
    video.addEventListener('seeked', onSeeked)
    video.addEventListener('play', onPlay)
    video.addEventListener('pause', onPause)
    layer.batchDraw()
    updateFrameFromVideo(true)
    return () => {
      video.removeEventListener('seeked', onSeeked)
      video.removeEventListener('play', onPlay)
      video.removeEventListener('pause', onPause)
    }
  }, [videoRef, layerRef, playing, updateFrameFromVideo])

  const play = useCallback(() => {
    void videoRef.current?.play()
  }, [videoRef])
  const pause = useCallback(() => {
    videoRef.current?.pause()
  }, [videoRef])
  const togglePlay = useCallback(() => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) void v.play()
    else v.pause()
  }, [videoRef])
  const seekToFrame = useCallback(
    (frame: number) => {
      const video = videoRef.current
      if (!video || framerate <= 0) return
      const f = clampFrame(frame, framesCount)
      video.currentTime = Math.max(0, (f - 0.5) / framerate)
    },
    [videoRef, framerate, framesCount],
  )

  // 同步 speed 到 video.playbackRate
  useEffect(() => {
    const video = videoRef.current
    if (video && ready) video.playbackRate = speed
  }, [videoRef, speed, ready])

  // 同步 loop 到 video.loop
  useEffect(() => {
    const video = videoRef.current
    if (video && ready) video.loop = loop
  }, [videoRef, loop, ready])

  const toggleLoop = useCallback(() => setLoop((prev) => !prev), [])

  return {
    videoEl: videoRef.current,
    videoWidth,
    videoHeight,
    currentFrame,
    currentTime,
    framerate,
    framesCount,
    duration,
    playing,
    ready,
    play,
    pause,
    togglePlay,
    seekToFrame,
    speed,
    setSpeed,
    loop,
    toggleLoop,
  }
}
