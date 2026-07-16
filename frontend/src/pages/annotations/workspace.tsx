import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Alert,
  Button,
  Card,
  Divider,
  Modal,
  Result,
  Space,
  Spin,
  Tag,
  Tooltip,
  Typography,
} from 'antd'
import { ArrowLeftOutlined, EditOutlined, QuestionCircleOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  cancelAnnotation,
  getAnnotationProjectDetail,
  getAnnotationTaskDetail,
  getMyProjectTaskIds,
  getNextAnnotationTask,
  submitAnnotation,
} from '@/services/annotations'
import { getMessageInstance } from '@/utils/messageHolder'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import {
  parseConfigTree,
  findNodes,
  toControlConfig,
  toObjectConfig,
  toRelationConfig,
  extractLabels,
  SPATIAL_CONTROL_TYPES,
  type ConfigNode,
} from './utils/parseLabelConfig'
import { serializeRegions } from './utils/serializeRegions'
import { validateAnnotationResults } from './utils/validation'
import { useAnnotationRegions } from './hooks/useAnnotationRegions'
import { useAnnotationRelations } from './hooks/useAnnotationRelations'
import AnnotationGuideline from './components/AnnotationGuideline'
import TaskNavigator from './components/TaskNavigator'
import ObjectDetectionAnnotator from './components/ObjectDetectionAnnotator'
import ImageSegmentationAnnotator from './components/ImageSegmentationAnnotator'
import KeyPointAnnotator from './components/KeyPointAnnotator'
import EllipseAnnotator from './components/EllipseAnnotator'
import BrushAnnotator from './components/BrushAnnotator'
import NerTextAnnotator from './components/NerTextAnnotator'
import ConfigRenderer, { type WorkspaceContext } from './components/ConfigRenderer'

// ── Hotkeys ─────────────────────────────────────────────────────────────────

const HOTKEYS: Array<{ key: string; label: string }> = [
  { key: '1-9', label: '选择标签' },
  { key: 'Enter', label: '提交当前标注 (Ctrl+Enter)' },
  { key: '← / →', label: '上一个 / 下一个任务' },
  { key: 'Ctrl+Z', label: '撤销' },
  { key: 'Space (按住)', label: '临时平移画布' },
  { key: '滚轮', label: '以鼠标为锚点缩放' },
]

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

  const tag = objectNode?.tag

  if (tag === 'Image') {
    switch (config.type) {
      case 'rectangle':
      case 'rectanglelabels':
        return <ObjectDetectionAnnotator key={config.name} {...sharedProps} relations={relations} />
      case 'polygon':
      case 'polygonlabels':
        return (
          <ImageSegmentationAnnotator key={config.name} {...sharedProps} relations={relations} />
        )
      case 'keypoint':
      case 'keypointlabels':
        return <KeyPointAnnotator key={config.name} {...sharedProps} relations={relations} />
      case 'ellipse':
      case 'ellipselabels':
        return <EllipseAnnotator key={config.name} {...sharedProps} relations={relations} />
      case 'brush':
      case 'brushlabels':
        return <BrushAnnotator key={config.name} {...sharedProps} />
    }
  }

  if ((tag === 'Text' || tag === 'HyperText') && config.type === 'labels') {
    return <NerTextAnnotator key={config.name} {...sharedProps} />
  }

  return (
    <Result
      key={config.name}
      status="warning"
      title="当前控件暂未支持"
      subTitle={`${config.tag} (${config.type}) 对 ${tag ?? '未知'} 类型暂未实现`}
    />
  )
}

// ── Main Component ──────────────────────────────────────────────────────────

export default function AnnotationWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [taskIds, setTaskIds] = useState<string[]>([])
  const [cursor, setCursor] = useState(0)
  const [currentTask, setCurrentTask] = useState<AnnotationTask | null>(null)
  const [readOnly, setReadOnly] = useState(false)
  const [guidelineCollapsed, setGuidelineCollapsed] = useState(false)
  const [taskLoading, setTaskLoading] = useState(false)
  const [taskLoadFailed, setTaskLoadFailed] = useState(false)
  const [initialized, setInitialized] = useState(false)
  const [hotkeyHelpOpen, setHotkeyHelpOpen] = useState(false)
  const [globalResults, setGlobalResults] = useState<Record<string, AnnotationResultItem[]>>({})

  const taskId = currentTask?.id ?? ''
  const regionsHook = useAnnotationRegions({ taskId, readOnly })
  const relationsHook = useAnnotationRelations({ taskId, readOnly })

  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ['annotationProject', projectId],
    queryFn: () => getAnnotationProjectDetail(projectId!),
    enabled: !!projectId,
  })

  // ── Parse config tree ────────────────────────────────────────────────────

  const configTree = useMemo(() => {
    if (!project?.labelConfig) return null
    try {
      return parseConfigTree(project.labelConfig)
    } catch {
      return null
    }
  }, [project?.labelConfig])

  const spatialControls = useMemo(
    () =>
      configTree
        ? findNodes(
            configTree,
            (n) => !!n.controlType && SPATIAL_CONTROL_TYPES.includes(n.controlType!),
          )
        : [],
    [configTree],
  )

  const relationControls = useMemo(
    () => (configTree ? findNodes(configTree, (n) => n.type === 'relation') : []),
    [configTree],
  )

  const objectMap = useMemo(() => {
    const map = new Map<string, ConfigNode>()
    if (configTree) {
      for (const n of findNodes(configTree, (n) => n.type === 'object' && !!n.name)) {
        if (n.name) map.set(n.name, n)
      }
    }
    return map
  }, [configTree])

  // ── Mutations ─────────────────────────────────────────────────────────────

  const submitMutation = useMutation({
    mutationFn: ({ taskId: tid, result }: { taskId: string; result: AnnotationResultItem[] }) =>
      submitAnnotation(tid, { result }),
    onSuccess: () => {
      getMessageInstance()?.success('标注提交成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProject', projectId] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTasks'] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTaskSummary'] })
    },
  })

  const cancelMutation = useMutation({
    mutationFn: (tid: string) => cancelAnnotation(tid),
    onSuccess: () => {
      getMessageInstance()?.success('已撤销提交,可以重新标注')
      queryClient.invalidateQueries({ queryKey: ['annotationProject', projectId] })
    },
  })

  // ── Workspace context for ConfigRenderer ─────────────────────────────────

  const workspaceContext: WorkspaceContext | null = useMemo(() => {
    if (!currentTask) return null
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

  // ── Submit ────────────────────────────────────────────────────────────────

  const buildSubmitResult = useCallback((): AnnotationResultItem[] => {
    return serializeRegions(
      regionsHook.regions,
      spatialControls.map(toControlConfig),
      regionsHook.imageDimensions,
      globalResults,
      relationsHook.relations,
      relationControls.map(toRelationConfig),
    )
  }, [
    regionsHook.regions,
    regionsHook.imageDimensions,
    globalResults,
    spatialControls,
    relationsHook.relations,
    relationControls,
  ])

  // ── Task navigation ──────────────────────────────────────────────────────

  const loadTaskById = useCallback(
    async (tid: string) => {
      if (!projectId) return
      setTaskLoading(true)
      setTaskLoadFailed(false)
      try {
        const detail = await getAnnotationTaskDetail(tid)
        setCurrentTask(detail)
        setReadOnly(detail.status === 'completed')
        setGlobalResults({})
      } catch {
        setTaskLoadFailed(true)
        getMessageInstance()?.error('加载任务失败')
      } finally {
        setTaskLoading(false)
      }
    },
    [projectId],
  )

  const goPrev = useCallback(async () => {
    if (cursor <= 0) return
    const prev = cursor - 1
    setCursor(prev)
    await loadTaskById(taskIds[prev])
  }, [cursor, taskIds, loadTaskById])

  const goNext = useCallback(async () => {
    if (!projectId) return
    setTaskLoading(true)
    try {
      const next = await getNextAnnotationTask(projectId)
      if (next) {
        setTaskIds((prev) => (prev.includes(next.id) ? prev : [...prev, next.id]))
        setCurrentTask(next)
        setReadOnly(next.status === 'completed')
        setCursor(taskIds.indexOf(next.id) === -1 ? taskIds.length : taskIds.indexOf(next.id))
        return
      }
    } catch {
      /* fallthrough */
    } finally {
      setTaskLoading(false)
    }
    if (cursor < taskIds.length - 1) {
      const nxt = cursor + 1
      setCursor(nxt)
      await loadTaskById(taskIds[nxt])
      return
    }
    setCurrentTask(null)
  }, [cursor, taskIds, projectId, loadTaskById])

  const handleSubmit = useCallback(() => {
    if (!currentTask) return
    const result = buildSubmitResult()
    if (result.length === 0) {
      getMessageInstance()?.warning('请先完成标注')
      return
    }
    const allControls = configTree ? findNodes(configTree, (n) => n.controlType !== undefined) : []
    const issues = validateAnnotationResults(allControls.map(toControlConfig), result)
    if (issues.length > 0) {
      Modal.confirm({
        title: '标注未完成',
        content: (
          <ul style={{ paddingLeft: 20, margin: 0 }}>
            {issues.map((issue) => (
              <li key={issue.controlName}>{issue.message}</li>
            ))}
          </ul>
        ),
        okText: '仍然提交',
        cancelText: '继续标注',
        onOk: () => {
          submitMutation.mutate(
            { taskId: currentTask.id, result },
            {
              onSuccess: async () => {
                await goNext()
              },
            },
          )
        },
      })
      return
    }
    submitMutation.mutate(
      { taskId: currentTask.id, result },
      {
        onSuccess: async () => {
          await goNext()
        },
      },
    )
  }, [currentTask, buildSubmitResult, submitMutation, goNext, configTree])

  // ── Init ──────────────────────────────────────────────────────────────────

  useEffect(() => {
    if (!projectId || initialized) return
    setInitialized(true)
    void (async () => {
      setTaskLoading(true)
      try {
        const ids = await getMyProjectTaskIds(projectId)
        setTaskIds(ids)
        if (ids.length === 0) {
          setCurrentTask(null)
          return
        }
        const next = await getNextAnnotationTask(projectId)
        if (next) {
          setCurrentTask(next)
          setReadOnly(next.status === 'completed')
          const existingIdx = ids.indexOf(next.id)
          setCursor(
            existingIdx >= 0
              ? existingIdx
              : (() => {
                  setTaskIds((prev) => [...prev, next.id])
                  return ids.length
                })(),
          )
        } else {
          await loadTaskById(ids[0])
          setCursor(0)
        }
      } catch {
        setTaskLoadFailed(true)
        getMessageInstance()?.error('加载任务失败')
      } finally {
        setTaskLoading(false)
      }
    })()
  }, [projectId, initialized, loadTaskById])

  // Global hotkeys
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA') return
      if (e.altKey || e.ctrlKey || e.metaKey) return
      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        void goPrev()
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        void goNext()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [goPrev, goNext])

  // ── Loading / error / empty states ───────────────────────────────────────

  if (projectLoading || !project) {
    return (
      <div
        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}
      >
        <Spin />
      </div>
    )
  }

  if (taskLoadFailed) {
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

  if (initialized && !currentTask && !taskLoading) {
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

  // ── Classification-only workspace ────────────────────────────────────────

  if (currentTask && spatialControls.length === 0 && workspaceContext) {
    return (
      <ClassificationOnlyWorkspace
        task={currentTask}
        project={project}
        configTree={configTree!}
        context={workspaceContext}
        onSubmit={handleSubmit}
        submitting={submitMutation.isPending}
        readOnly={readOnly}
        guidelineCollapsed={guidelineCollapsed}
        onToggleGuideline={() => setGuidelineCollapsed(!guidelineCollapsed)}
        onBack={() => navigate('/annotations')}
        currentTaskIndex={cursor}
        totalTasks={taskIds.length || project.totalTasks || 0}
        completedTasks={project.completedTasks || 0}
        onPrev={goPrev}
        onNext={goNext}
        onHotkeyHelp={() => setHotkeyHelpOpen(true)}
        labels={configTree ? extractLabels(configTree) : []}
      />
    )
  }

  // ── Main workspace layout ────────────────────────────────────────────────

  if (!currentTask || !workspaceContext) {
    return (
      <div
        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}
      >
        <Spin />
      </div>
    )
  }

  const totalTasks = project.totalTasks || 0
  const completedTasks = project.completedTasks || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '8px 16px',
          borderBottom: '1px solid var(--ant-color-border)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/annotations')}>
            返回
          </Button>
          <span style={{ fontWeight: 500 }}>{project.name}</span>
          {readOnly && currentTask && <Tag color="green">已完成 - 只读</Tag>}
        </div>
        <Space>
          <TaskNavigator
            currentTaskIndex={cursor}
            totalTasks={taskIds.length || totalTasks}
            completedTasks={completedTasks}
            onPrev={goPrev}
            onNext={goNext}
            hasPrev={cursor > 0}
            hasNext={cursor < (taskIds.length || totalTasks) - 1 || true}
          />
          <Tooltip title="快捷键帮助">
            <Button
              type="text"
              icon={<QuestionCircleOutlined />}
              onClick={() => setHotkeyHelpOpen(true)}
            />
          </Tooltip>
        </Space>
        <Button type="text" onClick={() => setGuidelineCollapsed(!guidelineCollapsed)}>
          规范 {guidelineCollapsed ? '▸' : '▾'}
        </Button>
      </div>

      {/* Read-only alert */}
      {readOnly && currentTask && (
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
                    const fresh = await getAnnotationTaskDetail(currentTask.id)
                    setCurrentTask(fresh)
                    setReadOnly(fresh.status === 'completed')
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

      {/* Workspace Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Canvas Area — spatial controls */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {spatialControls.map((node) =>
            renderSpatialControl(
              node,
              objectMap,
              currentTask,
              readOnly,
              regionsHook,
              relationsHook.relations,
            ),
          )}
          {!currentTask && taskLoading && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
              <Spin />
            </div>
          )}
        </div>

        {/* Side Panel: ConfigRenderer handles layout + classification */}
        <div
          style={{
            width: 280,
            borderLeft: '1px solid var(--ant-color-border)',
            overflowY: 'auto',
            padding: 12,
            display: 'flex',
            flexDirection: 'column',
            gap: 12,
          }}
        >
          {configTree && <ConfigRenderer node={configTree} context={workspaceContext} />}

          {/* Relation controls (not rendered by ConfigRenderer — handled here) */}
          {relationControls.length > 0 && (
            <>
              <Divider style={{ margin: '4px 0' }}>关系标注</Divider>
              {relationControls.map((relNode) => {
                const relConfig = toRelationConfig(relNode)
                return (
                  <Card key={relConfig.name} size="small" title={relConfig.tag}>
                    {!readOnly && (
                      <Space direction="vertical" style={{ width: '100%' }} size="small">
                        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                          点击左侧区域列表中的一个区域作为源，再点击另一个作为目标来创建关系。
                        </Typography.Text>
                        {relConfig.choices.length > 0 && !relationsHook.selectedRelationId && (
                          <Space wrap>
                            {relConfig.choices.map((ch) => (
                              <Tag
                                key={ch.value}
                                color="blue"
                                style={{ cursor: 'pointer' }}
                                onClick={() => {
                                  if (regionsHook.selectedRegionId) {
                                    relationsHook.addRelation({
                                      id: crypto.randomUUID(),
                                      fromRegionId: regionsHook.selectedRegionId,
                                      toRegionId: '',
                                      label: ch.value,
                                      sourceControlName: relConfig.name,
                                    })
                                  }
                                }}
                              >
                                {ch.value}
                              </Tag>
                            ))}
                          </Space>
                        )}
                      </Space>
                    )}
                    {relationsHook.relations.length > 0 && (
                      <div style={{ marginTop: 8 }}>
                        {relationsHook.relations
                          .filter((r) => r.sourceControlName === relConfig.name)
                          .map((rel, i) => {
                            const fromRegion = regionsHook.regions.find(
                              (r) => r.id === rel.fromRegionId,
                            )
                            const toRegion = regionsHook.regions.find(
                              (r) => r.id === rel.toRegionId,
                            )
                            return (
                              <div
                                key={rel.id}
                                style={{
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 4,
                                  marginBottom: 4,
                                }}
                              >
                                <Tag color="blue">{rel.label || `关系${i + 1}`}</Tag>
                                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                                  {fromRegion?.label || '区域'} → {toRegion?.label || '区域'}
                                </Typography.Text>
                                {!readOnly && (
                                  <Button
                                    type="text"
                                    size="small"
                                    danger
                                    onClick={() => relationsHook.removeRelation(rel.id)}
                                  >
                                    ×
                                  </Button>
                                )}
                              </div>
                            )
                          })}
                      </div>
                    )}
                  </Card>
                )
              })}
            </>
          )}

          {/* Submit */}
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

        {/* Guidelines */}
        <AnnotationGuideline
          project={project}
          labels={configTree ? extractLabels(configTree) : []}
          collapsed={guidelineCollapsed}
          onToggle={() => setGuidelineCollapsed(!guidelineCollapsed)}
        />
      </div>

      <Modal
        open={hotkeyHelpOpen}
        title="快捷键"
        footer={null}
        onCancel={() => setHotkeyHelpOpen(false)}
      >
        <Card size="small">
          <Space direction="vertical" style={{ width: '100%' }}>
            {HOTKEYS.map((h) => (
              <Space key={h.key} style={{ width: '100%', justifyContent: 'space-between' }}>
                <Typography.Text type="secondary">{h.label}</Typography.Text>
                <Tag>{h.key}</Tag>
              </Space>
            ))}
          </Space>
        </Card>
      </Modal>
    </div>
  )
}

// ── Classification-Only Workspace ───────────────────────────────────────────

function ClassificationOnlyWorkspace({
  task: _task,
  project,
  configTree,
  context,
  onSubmit,
  submitting,
  readOnly,
  guidelineCollapsed,
  onToggleGuideline,
  onBack,
  currentTaskIndex,
  totalTasks,
  completedTasks,
  onPrev,
  onNext,
  onHotkeyHelp,
  labels,
}: {
  task: AnnotationTask
  project: NonNullable<ReturnType<typeof useQuery>['data']>
  configTree: ConfigNode
  context: WorkspaceContext
  onSubmit: () => void
  submitting: boolean
  readOnly: boolean
  guidelineCollapsed: boolean
  onToggleGuideline: () => void
  onBack: () => void
  currentTaskIndex: number
  totalTasks: number
  completedTasks: number
  onPrev: () => void
  onNext: () => void
  onHotkeyHelp: () => void
  labels: string[]
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '8px 16px',
          borderBottom: '1px solid var(--ant-color-border)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>
            返回
          </Button>
          <span style={{ fontWeight: 500 }}>{(project as { name: string }).name}</span>
          {readOnly && <Tag color="green">已完成 - 只读</Tag>}
        </div>
        <Space>
          <TaskNavigator
            currentTaskIndex={currentTaskIndex}
            totalTasks={totalTasks}
            completedTasks={completedTasks}
            onPrev={onPrev}
            onNext={onNext}
            hasPrev={currentTaskIndex > 0}
            hasNext={true}
          />
          <Tooltip title="快捷键帮助">
            <Button type="text" icon={<QuestionCircleOutlined />} onClick={onHotkeyHelp} />
          </Tooltip>
        </Space>
        <Button type="text" onClick={onToggleGuideline}>
          规范 {guidelineCollapsed ? '▸' : '▾'}
        </Button>
      </div>
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{ flex: 1, padding: 16, overflowY: 'auto' }}>
          <ConfigRenderer node={configTree} context={context} />
          {!readOnly && (
            <Button type="primary" onClick={onSubmit} loading={submitting} block>
              提交标注
            </Button>
          )}
        </div>
        <AnnotationGuideline
          project={project}
          labels={labels}
          collapsed={guidelineCollapsed}
          onToggle={onToggleGuideline}
        />
      </div>
    </div>
  )
}
