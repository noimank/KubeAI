import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Alert, Button, Modal, Result, Spin } from 'antd'
import { EditOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { getAnnotationProjectDetail } from '@/services/annotations'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import {
  toControlConfig,
  toObjectConfig,
  findNodes,
  type ConfigNode,
} from './utils/parseLabelConfig'
import { regionKindForControl } from './registry/tags'
import type { VisibilityState } from './utils/visibility'
import { useAnnotationRegions } from './hooks/useAnnotationRegions'
import { useAnnotationRelations } from './hooks/useAnnotationRelations'
import { useAnnotationConfig } from './hooks/useAnnotationConfig'
import { useAnnotationTask } from './hooks/useAnnotationTask'
import { useAnnotationSubmit } from './hooks/useAnnotationSubmit'
import AnnotationGuideline from './components/AnnotationGuideline'
import WorkspaceTopBar from './components/WorkspaceTopBar'
import HotkeyHelpModal from './components/HotkeyHelpModal'
import RelationPanel from './components/RelationPanel'
import UnsupportedTag from './components/UnsupportedTag'
import ObjectDetectionAnnotator from './components/ObjectDetectionAnnotator'
import ImageSegmentationAnnotator from './components/ImageSegmentationAnnotator'
import KeyPointAnnotator from './components/KeyPointAnnotator'
import EllipseAnnotator from './components/EllipseAnnotator'
import BrushAnnotator from './components/BrushAnnotator'
import VectorAnnotator from './components/VectorAnnotator'
import BitmaskAnnotator from './components/BitmaskAnnotator'
import MagicWandAnnotator from './components/MagicWandAnnotator'
import NerTextAnnotator from './components/NerTextAnnotator'
import ParagraphLabelsAnnotator from './components/ParagraphLabelsAnnotator'
import TimeSeriesLabelsAnnotator from './components/TimeSeriesLabelsAnnotator'
import AudioLabelsAnnotator from './components/AudioLabelsAnnotator'
import ChatViewer from './components/viewers/ChatViewer'
import ConfigRenderer, { type WorkspaceContext } from './components/ConfigRenderer'
import VideoAnnotator from './components/video/VideoAnnotator'
import { deserializeRegions } from './utils/deserializeRegions'
import type { VideoSerializeMeta } from './utils/serializeRegions'

// ── Spatial control dispatch ────────────────────────────────────────────────

function renderSpatialControl(
  node: ConfigNode,
  objectMap: Map<string, ConfigNode>,
  task: AnnotationTask,
  readOnly: boolean,
  regionsHook: ReturnType<typeof useAnnotationRegions>,
  relations: ReturnType<typeof useAnnotationRelations>['relations'],
) {
  const config = toControlConfig(node)
  const objectNode = objectMap.get(config.toName)
  const objectConfig = objectNode ? toObjectConfig(objectNode) : undefined
  const objectTag = objectNode?.tag
  const regionKind = regionKindForControl(config.tag)

  const sharedProps = {
    task,
    objectConfig,
    controlConfig: config,
    readOnly,
    regions: regionsHook.regions,
    selectedRegionId: regionsHook.selectedRegionId,
    imageDimensions: regionsHook.imageDimensions,
    onAddRegion: regionsHook.addRegion,
    onUpdateRegion: regionsHook.updateRegion,
    onDeleteRegion: regionsHook.removeRegion,
    onSelectRegion: regionsHook.selectRegion,
    onImageDimensionsChange: regionsHook.setImageDimensions,
  }

  if (objectTag === 'Image' && regionKind) {
    switch (regionKind) {
      case 'rectangle':
        return <ObjectDetectionAnnotator key={config.name} {...sharedProps} relations={relations} />
      case 'polygon':
        return (
          <ImageSegmentationAnnotator key={config.name} {...sharedProps} relations={relations} />
        )
      case 'keypoint':
        return <KeyPointAnnotator key={config.name} {...sharedProps} relations={relations} />
      case 'ellipse':
        return <EllipseAnnotator key={config.name} {...sharedProps} relations={relations} />
      case 'brush':
        return <BrushAnnotator key={config.name} {...sharedProps} />
      case 'vector':
        return <VectorAnnotator key={config.name} {...sharedProps} />
      case 'bitmask':
        return <BitmaskAnnotator key={config.name} {...sharedProps} />
      case 'magicwand':
        return <MagicWandAnnotator key={config.name} {...sharedProps} />
    }
  }

  if ((objectTag === 'Text' || objectTag === 'HyperText') && regionKind === 'textspan') {
    return <NerTextAnnotator key={config.name} {...sharedProps} />
  }

  // Audio Labels：在波形上选区间（Labels 控件目标为 Audio）
  if (objectTag === 'Audio' && (config.tag === 'Labels' || config.tag === 'HyperTextLabels')) {
    return <AudioLabelsAnnotator key={config.name} {...sharedProps} />
  }

  if (objectTag === 'Paragraphs' && regionKind === 'paragraphspan') {
    return <ParagraphLabelsAnnotator key={config.name} {...sharedProps} />
  }

  if (objectTag === 'TimeSeries' && regionKind === 'timeseries' && objectNode) {
    return (
      <TimeSeriesLabelsAnnotator
        key={config.name}
        task={task}
        objectNode={objectNode}
        controlConfig={config}
        readOnly={readOnly}
        regions={regionsHook.regions}
        selectedRegionId={regionsHook.selectedRegionId}
        onAddRegion={regionsHook.addRegion}
        onDeleteRegion={regionsHook.removeRegion}
        onSelectRegion={regionsHook.selectRegion}
      />
    )
  }

  return <UnsupportedTag key={config.name} tag={config.tag} />
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function AnnotationWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()

  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ['annotationProject', projectId],
    queryFn: () => getAnnotationProjectDetail(projectId!),
    enabled: !!projectId,
  })

  const task = useAnnotationTask(projectId)
  const { currentTask, readOnly } = task
  const taskId = currentTask?.id ?? ''
  const regionsHook = useAnnotationRegions({ taskId, readOnly })
  const relationsHook = useAnnotationRelations({ taskId, readOnly })
  const { configTree, spatialControls, relationControls, objectMap, labels } =
    useAnnotationConfig(project)

  // 按 <Video> 对象聚合视频空间控件，每个 Video 渲染单个 VideoAnnotator（共享唯一 <video>）
  const videoGroups = useMemo(() => {
    if (!configTree) return []
    const videos = findNodes(
      configTree,
      (n) => n.type === 'object' && n.tag === 'Video' && !!n.name,
    )
    return videos
      .map((v) => ({
        videoNode: v,
        controls: spatialControls.filter((c) => c.attrs.toname === v.name),
      }))
      .filter((g) => g.controls.length > 0)
  }, [configTree, spatialControls])

  const videoConsumedControlNames = useMemo(
    () =>
      new Set(
        videoGroups.flatMap((g) => g.controls.map((c) => c.name).filter((n): n is string => !!n)),
      ),
    [videoGroups],
  )

  const [globalResults, setGlobalResults] = useState<Record<string, AnnotationResultItem[]>>({})
  const [videoMetaByObject, setVideoMetaByObject] = useState<Record<string, VideoSerializeMeta>>({})
  const [guidelineCollapsed, setGuidelineCollapsed] = useState(false)
  const [hotkeyHelpOpen, setHotkeyHelpOpen] = useState(false)

  const { submitMutation, cancelMutation, handleSubmit } = useAnnotationSubmit({
    projectId,
    currentTask,
    configTree,
    spatialControls,
    relationControls,
    regionsHook,
    relationsHook,
    globalResults,
    videoMetaByObject,
    goNext: task.goNext,
  })

  // 切换任务时重置全局分类结果
  useEffect(() => {
    setGlobalResults({})
  }, [taskId])

  // 只读回显：反序列化已提交结果到 regions（修复 workspace 提交后不回显的既有缺口）
  useEffect(() => {
    regionsHook.restoreRegions(deserializeRegions(currentTask?.result))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskId])

  const workspaceContext: WorkspaceContext | null = useMemo(() => {
    if (!currentTask) return null
    const selectedRegion =
      regionsHook.regions.find((r) => r.id === regionsHook.selectedRegionId) ?? null
    const selectedRegionRole =
      selectedRegion?.value.kind === 'message' ? selectedRegion.value.role : undefined
    const visibility: VisibilityState = {
      selectedRegion,
      regions: regionsHook.regions,
      results: [
        ...Object.values(globalResults).flat(),
        ...regionsHook.regions.flatMap((r) => Object.values(r.perRegionResults)),
      ],
      selectedRegionRole,
    }
    return {
      task: currentTask,
      readOnly,
      submitting: submitMutation.isPending,
      regions: regionsHook.regions,
      selectedRegionId: regionsHook.selectedRegionId,
      imageDimensions: regionsHook.imageDimensions,
      globalResults,
      onPerRegionResult: (controlName) => (regionId, result) =>
        regionsHook.setRegionResult(regionId, controlName, result),
      onGlobalResult: (controlName) => (results) =>
        setGlobalResults((prev) => ({ ...prev, [controlName]: results })),
      getRegionResult: (regionId, controlName) =>
        regionsHook.getRegionResult(regionId, controlName),
      hasSpatialControls: spatialControls.length > 0,
      objectMap,
      visibility,
    }
  }, [
    currentTask,
    readOnly,
    submitMutation.isPending,
    regionsHook,
    globalResults,
    spatialControls.length,
    objectMap,
  ])

  // ── States ──────────────────────────────────────────────────────────────────

  if (projectLoading || !project) {
    return (
      <div
        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}
      >
        <Spin />
      </div>
    )
  }

  if (task.taskLoadFailed) {
    return (
      <div style={{ padding: 48 }}>
        <Result
          status="error"
          title="加载失败"
          subTitle="标注任务加载失败，请稍后重试"
          extra={
            <Button type="primary" onClick={() => window.location.reload()}>
              重新加载
            </Button>
          }
        />
      </div>
    )
  }

  if (task.initialized && !currentTask && !task.taskLoading) {
    return (
      <div style={{ padding: 48 }}>
        <Result
          status="success"
          title="全部完成"
          subTitle="该项目中没有更多分配给你的标注任务"
          extra={
            <Button type="primary" onClick={() => navigate('/annotations')}>
              返回标注列表
            </Button>
          }
        />
      </div>
    )
  }

  if (!currentTask || !workspaceContext) {
    return (
      <div
        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}
      >
        <Spin />
      </div>
    )
  }

  const totalTasks = task.taskIds.length || project.totalTasks || 0
  const chatObjects = configTree
    ? findNodes(configTree, (n) => n.type === 'object' && n.tag === 'Chat')
    : []
  // 画布面板承载空间控件与交互式对象（Chat 消息即区域）
  const hasCanvasPane = spatialControls.length > 0 || chatObjects.length > 0

  // ── Layout（空间/分类两种形态合并：无 canvas 控件时 DOM 面板全宽）─────────

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <WorkspaceTopBar
        projectName={project.name}
        readOnly={readOnly}
        onBack={() => navigate('/annotations')}
        cursor={task.cursor}
        totalTasks={totalTasks}
        completedTasks={project.completedTasks || 0}
        onPrev={task.goPrev}
        onNext={task.goNext}
        hasPrev={task.cursor > 0}
        hasNext={task.cursor < totalTasks - 1 || true}
        onHotkeyHelp={() => setHotkeyHelpOpen(true)}
        guidelineCollapsed={guidelineCollapsed}
        onToggleGuideline={() => setGuidelineCollapsed(!guidelineCollapsed)}
      />

      {readOnly && (
        <Alert
          type="info"
          showIcon
          message="该任务已提交,当前为只读预览"
          action={
            <Button
              size="small"
              type="primary"
              icon={<EditOutlined />}
              loading={cancelMutation.isPending}
              onClick={() => {
                Modal.confirm({
                  title: '重新标注?',
                  content: '撤销当前提交后任务会回到「进行中」状态,可继续编辑。',
                  okText: '重新标注',
                  onOk: async () => {
                    await cancelMutation.mutateAsync(currentTask.id)
                    await task.refreshCurrentTask()
                  },
                })
              }}
            >
              重新标注
            </Button>
          }
          style={{ margin: '8px 16px 0' }}
        />
      )}

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {hasCanvasPane && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            {videoGroups.map((g) => (
              <VideoAnnotator
                key={g.videoNode.name}
                videoNode={g.videoNode}
                controls={g.controls}
                task={currentTask}
                readOnly={readOnly}
                regionsHook={regionsHook}
                onVideoMeta={(meta) =>
                  setVideoMetaByObject((prev) => ({ ...prev, [g.videoNode.name!]: meta }))
                }
              />
            ))}
            {spatialControls
              .filter((node) => !videoConsumedControlNames.has(node.name!))
              .map((node) =>
                renderSpatialControl(
                  node,
                  objectMap,
                  currentTask,
                  readOnly,
                  regionsHook,
                  relationsHook.relations,
                ),
              )}
            {chatObjects.map((node) => (
              <div key={node.name} style={{ flex: 1, overflow: 'auto', padding: 12 }}>
                <ChatViewer
                  task={currentTask}
                  objectConfig={toObjectConfig(node)}
                  regions={regionsHook.regions}
                  selectedRegionId={regionsHook.selectedRegionId}
                  onAddRegion={regionsHook.addRegion}
                  onSelectRegion={regionsHook.selectRegion}
                  readOnly={readOnly}
                />
              </div>
            ))}
            {!currentTask && task.taskLoading && (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
                <Spin />
              </div>
            )}
          </div>
        )}

        <div
          style={{
            flex: hasCanvasPane ? '0 0 280px' : 1,
            borderLeft: hasCanvasPane ? '1px solid var(--ant-color-border)' : undefined,
            overflowY: 'auto',
            padding: 16,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          {configTree && <ConfigRenderer node={configTree} context={workspaceContext} />}

          <RelationPanel
            relationControls={relationControls}
            regions={regionsHook.regions}
            selectedRegionId={regionsHook.selectedRegionId}
            relations={relationsHook.relations}
            selectedRelationId={relationsHook.selectedRelationId}
            readOnly={readOnly}
            onAddRelation={relationsHook.addRelation}
            onRemoveRelation={relationsHook.removeRelation}
          />

          {!readOnly && (
            <Button
              type="primary"
              size="large"
              block
              onClick={handleSubmit}
              loading={submitMutation.isPending}
              disabled={
                regionsHook.regions.length === 0 &&
                Object.values(globalResults).every((a) => a.length === 0)
              }
            >
              提交标注 ({regionsHook.regions.length})
            </Button>
          )}
        </div>

        <AnnotationGuideline
          project={project}
          labels={labels}
          collapsed={guidelineCollapsed}
          onToggle={() => setGuidelineCollapsed(!guidelineCollapsed)}
        />
      </div>

      <HotkeyHelpModal open={hotkeyHelpOpen} onClose={() => setHotkeyHelpOpen(false)} />
    </div>
  )
}
