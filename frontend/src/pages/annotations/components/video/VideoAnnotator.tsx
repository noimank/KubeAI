import { useRef } from 'react'
import type Konva from 'konva'
import { toControlConfig, type ConfigNode } from '../../utils/parseLabelConfig'
import type { AnnotationTask } from '@/types/annotation'
import type { useAnnotationRegions } from '../../hooks/useAnnotationRegions'
import { appendAuthToken } from '@/utils/constants'
import { useVideoPlayer, type VideoMeta } from './useVideoPlayer'
import { useVideoStage } from './useVideoStage'
import { VideoPlayerContext } from './VideoPlayerContext'
import VideoRectangleLayer from './VideoRectangleLayer'
import VideoStage from './VideoStage'
import VideoTimeline from './VideoTimeline'
import TimelineLabelsTrack from './TimelineLabelsTrack'

interface VideoAnnotatorProps {
  videoNode: ConfigNode
  /** 指向本 Video 对象的所有空间控件（VideoRectangle / TimelineLabels / 外部 Labels） */
  controls: ConfigNode[]
  task: AnnotationTask
  readOnly: boolean
  regionsHook: ReturnType<typeof useAnnotationRegions>
  onVideoMeta: (meta: VideoMeta) => void
}

/**
 * 单个 <Video> 对象的统一标注容器：拥有唯一 <video> + Konva layer，按对象分组聚合
 * 所有指向它的控件（VideoRectangle 画框层 + TimelineLabels 时间轴 + 外部 Labels 标签源），
 * 绝不每个控件各渲染一个 video。video 元素隐藏但保留解码（供 Konva.Image drawImage）。
 */
export default function VideoAnnotator({
  videoNode,
  controls,
  task,
  readOnly,
  regionsHook,
  onVideoMeta,
}: VideoAnnotatorProps) {
  const field = videoNode.field ?? videoNode.attrs.value?.replace(/^\$/, '') ?? 'video'
  const url = (task.data?.[field] as string | undefined) ?? ''
  const framerate = Number(videoNode.attrs.framerate ?? 24) || 24
  const isMuted = videoNode.attrs.muted !== 'false'
  const videoHeight = Number(videoNode.attrs.height) || undefined
  const defaultSpeed = Number(videoNode.attrs.defaultplaybackspeed) || 1

  const videoRef = useRef<HTMLVideoElement>(null)
  const layerRef = useRef<Konva.Layer | null>(null)
  const player = useVideoPlayer(videoRef, layerRef, url, framerate, onVideoMeta, defaultSpeed)
  const stage = useVideoStage(player.videoWidth, player.videoHeight)

  const videoRectCtrl = controls.find((c) => c.tag === 'VideoRectangle')
  const timelineCtrls = controls.filter((c) => c.tag === 'TimelineLabels')
  const labelsCtrls = controls.filter((c) => c.tag === 'Labels' || c.tag === 'HyperTextLabels')
  const rectLabelChoices = labelsCtrls.flatMap((c) => (c.choices ?? []).map((ch) => ch.value))
  const showTimeline = timelineCtrls.length > 0 || !!videoRectCtrl

  return (
    <VideoPlayerContext.Provider value={player}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1, minHeight: 0 }}>
        {/* 隐藏 video：保留解码供 Konva.Image，但不在视口占用空间 */}
        <video
          ref={videoRef}
          src={appendAuthToken(url)}
          crossOrigin="anonymous"
          muted={isMuted}
          playsInline
          style={{ position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }}
        />
        {videoRectCtrl ? (
          <VideoRectangleLayer
            controlConfig={toControlConfig(videoRectCtrl)}
            regions={regionsHook.regions}
            selectedRegionId={regionsHook.selectedRegionId}
            readOnly={readOnly}
            rectLabels={rectLabelChoices}
            videoEl={player.videoEl}
            stageController={stage}
            layerRef={layerRef}
            onAddRegion={regionsHook.addRegion}
            onUpdateRegion={regionsHook.updateRegion}
            onDeleteRegion={regionsHook.removeRegion}
            onSelectRegion={regionsHook.selectRegion}
          />
        ) : (
          player.ready && (
            <div
              style={{
                flex: 1,
                minHeight: videoHeight ?? 300,
                display: 'flex',
                flexDirection: 'column',
              }}
            >
              <VideoStage
                videoEl={player.videoEl}
                naturalWidth={player.videoWidth}
                naturalHeight={player.videoHeight}
                controller={stage}
                layerRef={layerRef}
                renderContent={() => null}
              />
            </div>
          )
        )}
        {showTimeline && (
          <VideoTimeline>
            {timelineCtrls.map((c) => (
              <TimelineLabelsTrack
                key={c.name}
                controlConfig={toControlConfig(c)}
                regions={regionsHook.regions}
                selectedRegionId={regionsHook.selectedRegionId}
                readOnly={readOnly}
                onAddRegion={regionsHook.addRegion}
                onDeleteRegion={regionsHook.removeRegion}
                onSelectRegion={regionsHook.selectRegion}
              />
            ))}
          </VideoTimeline>
        )}
      </div>
    </VideoPlayerContext.Provider>
  )
}
