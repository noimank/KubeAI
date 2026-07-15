import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Alert, Button, Card, Divider, Modal, Result, Space, Spin, Tag, Tooltip, Typography,
} from 'antd'
import {
  ArrowLeftOutlined, EditOutlined, QuestionCircleOutlined,
} from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  cancelAnnotation, getAnnotationProjectDetail, getAnnotationTaskDetail,
  getMyProjectTaskIds, getNextAnnotationTask, submitAnnotation,
} from '@/services/annotations'
import { getMessageInstance } from '@/utils/messageHolder'
import type { AnnotationResultItem, AnnotationTask } from '@/types/annotation'
import {
  parseLabelConfig, SPATIAL_CONTROL_TYPES,
  type LabelStudioControlConfig, type LabelStudioObjectConfig,
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
import TextAreaAnnotator from './components/TextAreaAnnotator'
import ChoicesAnnotator from './components/ChoicesAnnotator'
import FormControlAnnotator from './components/FormControlAnnotator'
import { appendAuthToken } from '@/utils/constants'
import type { AnnotationRegion, ImageDimensions } from './hooks/useAnnotationRegions'

// ── Helpers ─────────────────────────────────────────────────────────────────

function isSpatial(ctrl: LabelStudioControlConfig): boolean {
  return SPATIAL_CONTROL_TYPES.includes(ctrl.type)
}

// ── Hotkeys ─────────────────────────────────────────────────────────────────

const HOTKEYS: Array<{ key: string; label: string }> = [
  { key: '1-9', label: '选择标签' },
  { key: 'Enter', label: '提交当前标注 (Ctrl+Enter)' },
  { key: '← / →', label: '上一个 / 下一个任务' },
  { key: 'Ctrl+Z', label: '撤销' },
  { key: 'Space (按住)', label: '临时平移画布' },
  { key: '滚轮', label: '以鼠标为锚点缩放' },
]

// ── Classification control switch ───────────────────────────────────────────

function renderClassificationControl(
  ctrl: LabelStudioControlConfig,
  task: AnnotationTask,
  objectConfig: LabelStudioObjectConfig | undefined,
  readOnly: boolean,
  perRegion: boolean,
  selectedRegionId: string | null,
  currentRegionResult: AnnotationResultItem | null,
  onPerRegionResult: ((regionId: string, result: AnnotationResultItem | null) => void) | undefined,
  onGlobalResult: ((results: AnnotationResultItem[]) => void) | undefined,
  submitting: boolean,
  /** Selected region for per-region crop preview */
  selectedRegion?: AnnotationRegion | null,
  /** Image dimensions for crop positioning */
  imageDimensions?: ImageDimensions | null,
  /** Image URL for the task's data object */
  imageUrl?: string,
) {
  switch (ctrl.type) {
    case 'textarea': {
      const textValue = currentRegionResult?.value?.text as string[] | undefined
      return (
        <TextAreaAnnotator
          task={task} labels={ctrl.choices.map((c) => c.value)}
          objectConfig={objectConfig} controlConfig={ctrl} readOnly={readOnly}
          perRegion={perRegion} selectedRegionId={selectedRegionId}
          currentRegionText={textValue?.[0] ?? null}
          onPerRegionResult={onPerRegionResult}
          onSubmit={onGlobalResult ? (r) => onGlobalResult(r) : () => {}}
          submitting={submitting}
          selectedRegion={selectedRegion ?? null}
          imageDimensions={imageDimensions ?? null}
          imageUrl={imageUrl}
        />
      )
    }
    case 'choices': {
      const choiceValue = currentRegionResult?.value?.choices as string[] | undefined
      return (
        <ChoicesAnnotator
          task={task} labels={ctrl.choices.map((c) => c.value)}
          objectConfig={objectConfig} controlConfig={ctrl} readOnly={readOnly}
          perRegion={perRegion} selectedRegionId={selectedRegionId}
          currentRegionChoices={choiceValue ?? null}
          onPerRegionResult={onPerRegionResult}
          onSubmit={onGlobalResult ? (r) => onGlobalResult(r) : () => {}}
          submitting={submitting}
          selectedRegion={selectedRegion ?? null}
          imageDimensions={imageDimensions ?? null}
          imageUrl={imageUrl}
        />
      )
    }
    case 'rating':
    case 'number':
    case 'taxonomy':
      return (
        <FormControlAnnotator
          task={task} labels={ctrl.choices.map((c) => c.value)}
          objectConfig={objectConfig} controlConfig={ctrl} readOnly={readOnly}
          perRegion={perRegion} selectedRegionId={selectedRegionId}
          currentRegionValue={currentRegionResult?.value ?? null}
          onPerRegionResult={onPerRegionResult}
          onSubmit={onGlobalResult ? (r) => onGlobalResult(r) : () => {}}
          submitting={submitting}
          selectedRegion={selectedRegion ?? null}
          imageDimensions={imageDimensions ?? null}
          imageUrl={imageUrl}
        />
      )
    default:
      return (
        <Result status="warning" title="暂未支持" subTitle={`${ctrl.tag} 控件尚未实现`} />
      )
  }
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

  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ['annotationProject', projectId],
    queryFn: () => getAnnotationProjectDetail(projectId!),
    enabled: !!projectId,
  })

  const parsedConfig = useMemo(
    () => (project?.labelConfig ? parseLabelConfig(project.labelConfig) : null),
    [project?.labelConfig],
  )

  const spatialControls = useMemo(
    () => parsedConfig?.controls.filter(isSpatial) ?? [],
    [parsedConfig],
  )
  const classificationControls = useMemo(
    () => parsedConfig?.controls.filter((c) => !isSpatial(c)) ?? [],
    [parsedConfig],
  )
  const perRegionControls = useMemo(
    () => classificationControls.filter((c) => c.perRegion),
    [classificationControls],
  )
  const globalClassificationControls = useMemo(
    () => classificationControls.filter((c) => !c.perRegion),
    [classificationControls],
  )

  // Resolve objects from parsed config — keep as Map for lookup
  const objectMap = useMemo(
    () => new Map((parsedConfig?.objects ?? []).map((o) => [o.name, o])),
    [parsedConfig?.objects],
  )

  // Relation controls
  const relationControls = useMemo(
    () => parsedConfig?.relations ?? [],
    [parsedConfig?.relations],
  )

  const relationsHook = useAnnotationRelations({ taskId, readOnly })

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

  // ── Submit ────────────────────────────────────────────────────────────────

  const buildSubmitResult = useCallback((): AnnotationResultItem[] => {
    return serializeRegions(
      regionsHook.regions,
      parsedConfig?.controls ?? [],
      regionsHook.imageDimensions,
      globalResults,
      relationsHook.relations,
      relationControls,
    )
  }, [regionsHook.regions, regionsHook.imageDimensions, globalResults, parsedConfig?.controls, relationsHook.relations, relationControls])

  // ── Per-region result handler ─────────────────────────────────────────────

  const handlePerRegionResult = useCallback(
    (controlName: string) => (regionId: string, result: AnnotationResultItem | null) => {
      regionsHook.setRegionResult(regionId, controlName, result)
    },
    [regionsHook],
  )

  // ── Global result handler ─────────────────────────────────────────────────

  const handleGlobalResult = useCallback(
    (controlName: string) => (results: AnnotationResultItem[]) => {
      setGlobalResults((prev) => ({ ...prev, [controlName]: results }))
    },
    [],
  )

  // ── Task navigation ──────────────────────────────────────────────────────

  const loadTaskById = useCallback(async (tid: string) => {
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
  }, [projectId])

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
    } catch { /* fallthrough */ }
    finally { setTaskLoading(false) }
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
    // Validation: check required controls
    const issues = validateAnnotationResults(parsedConfig?.controls ?? [], result)
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
            { onSuccess: async () => { await goNext() } },
          )
        },
      })
      return
    }
    submitMutation.mutate(
      { taskId: currentTask.id, result },
      { onSuccess: async () => { await goNext() } },
    )
  }, [currentTask, buildSubmitResult, submitMutation, goNext, parsedConfig?.controls])

  useEffect(() => {
    if (!projectId || initialized) return
    setInitialized(true)
    void (async () => {
      setTaskLoading(true)
      try {
        const ids = await getMyProjectTaskIds(projectId)
        setTaskIds(ids)
        if (ids.length === 0) { setCurrentTask(null); return }
        const next = await getNextAnnotationTask(projectId)
        if (next) {
          setCurrentTask(next)
          setReadOnly(next.status === 'completed')
          const existingIdx = ids.indexOf(next.id)
          setCursor(existingIdx >= 0 ? existingIdx : (() => {
            setTaskIds((prev) => [...prev, next.id])
            return ids.length
          })())
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
      if (e.key === 'ArrowLeft') { e.preventDefault(); void goPrev() }
      else if (e.key === 'ArrowRight') { e.preventDefault(); void goNext() }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [goPrev, goNext])

  // ── Loading / error / empty states ───────────────────────────────────────

  if (projectLoading || !project) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <Spin />
      </div>
    )
  }

  if (taskLoadFailed) {
    return (
      <div style={{ padding: 48 }}>
        <Result
          status="error" title="加载失败" subTitle="标注任务加载失败，请稍后重试"
          extra={<Button type="primary" onClick={() => window.location.reload()}>重新加载</Button>}
        />
      </div>
    )
  }

  if (initialized && !currentTask && !taskLoading) {
    return (
      <div style={{ padding: 48 }}>
        <Result
          status="success" title="全部完成" subTitle="该项目中没有更多分配给你的标注任务"
          extra={<Button type="primary" onClick={() => navigate('/annotations')}>返回标注列表</Button>}
        />
      </div>
    )
  }

  // ── No spatial controls → pure classification workspace ──────────────────

  if (currentTask && spatialControls.length === 0) {
    return (
      <ClassificationOnlyWorkspace
        task={currentTask} project={project}
        objectConfig={parsedConfig?.objects[0]}
        controls={classificationControls}
        onSubmit={handleSubmit} submitting={submitMutation.isPending} readOnly={readOnly}
        guidelineCollapsed={guidelineCollapsed}
        onToggleGuideline={() => setGuidelineCollapsed(!guidelineCollapsed)}
        onBack={() => navigate('/annotations')}
        currentTaskIndex={cursor}
        totalTasks={taskIds.length || project.totalTasks || 0}
        completedTasks={project.completedTasks || 0}
        onPrev={goPrev} onNext={goNext}
        onHotkeyHelp={() => setHotkeyHelpOpen(true)}
        renderControl={(ctrl) => {
            const objCfg = parsedConfig?.objects[0]
            const imgUrl = objCfg ? (currentTask.data?.[objCfg.field] as string | undefined) : undefined
            const selRegion = regionsHook.selectedRegionId
              ? regionsHook.regions.find((r) => r.id === regionsHook.selectedRegionId) ?? null
              : null
            return renderClassificationControl(
              ctrl, currentTask, objCfg, readOnly,
              !!ctrl.perRegion, regionsHook.selectedRegionId,
              regionsHook.selectedRegionId
                ? regionsHook.getRegionResult(regionsHook.selectedRegionId, ctrl.name)
                : null,
              ctrl.perRegion ? handlePerRegionResult(ctrl.name) : undefined,
              ctrl.perRegion ? undefined : handleGlobalResult(ctrl.name),
              submitMutation.isPending,
              ctrl.perRegion ? selRegion : null,
              ctrl.perRegion ? regionsHook.imageDimensions : null,
              ctrl.perRegion ? imgUrl : undefined,
            )
          }}
      />
    )
  }

  // ── Main workspace layout ────────────────────────────────────────────────

  if (!currentTask) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <Spin />
      </div>
    )
  }

  const totalTasks = project.totalTasks || 0
  const completedTasks = project.completedTasks || 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Top Bar */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '8px 16px', borderBottom: '1px solid var(--ant-color-border)',
      }}>
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
            onPrev={goPrev} onNext={goNext}
            hasPrev={cursor > 0}
            hasNext={cursor < (taskIds.length || totalTasks) - 1 || true}
          />
          <Tooltip title="快捷键帮助">
            <Button type="text" icon={<QuestionCircleOutlined />} onClick={() => setHotkeyHelpOpen(true)} />
          </Tooltip>
        </Space>
        <Button type="text" onClick={() => setGuidelineCollapsed(!guidelineCollapsed)}>
          规范 {guidelineCollapsed ? '▸' : '▾'}
        </Button>
      </div>

      {/* Read-only alert */}
      {readOnly && currentTask && (
        <Alert
          type="info" showIcon
          message="该任务已提交,当前为只读预览"
          action={
            <Button size="small" type="primary" icon={<EditOutlined />}
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
            >重新标注</Button>
          }
          style={{ margin: '8px 16px 0' }}
        />
      )}

      {/* Workspace Body */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Canvas Area — renders spatial controls */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {currentTask && spatialControls.map((spatialCtrl) => {
            const objectConfig = objectMap.get(spatialCtrl.toName)
            const sharedProps = {
              task: currentTask,
              objectConfig,
              controlConfig: spatialCtrl,
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

            const { type } = spatialCtrl
            const tag = objectConfig?.tag

            // Image-based spatial controls
            if (tag === 'Image') {
              switch (type) {
                case 'rectangle':
                case 'rectanglelabels':
                  return <ObjectDetectionAnnotator key={spatialCtrl.name} {...sharedProps} relations={relationsHook.relations} />
                case 'polygon':
                case 'polygonlabels':
                  return <ImageSegmentationAnnotator key={spatialCtrl.name} {...sharedProps} relations={relationsHook.relations} />
                case 'keypoint':
                case 'keypointlabels':
                  return <KeyPointAnnotator key={spatialCtrl.name} {...sharedProps} relations={relationsHook.relations} />
                case 'ellipse':
                case 'ellipselabels':
                  return <EllipseAnnotator key={spatialCtrl.name} {...sharedProps} relations={relationsHook.relations} />
                case 'brush':
                case 'brushlabels':
                  return <BrushAnnotator key={spatialCtrl.name} {...sharedProps} />
              }
            }

            // Text-based NLP labels
            if ((tag === 'Text' || tag === 'HyperText') && type === 'labels') {
              return <NerTextAnnotator key={spatialCtrl.name} {...sharedProps} />
            }

            return (
              <Result
                key={spatialCtrl.name}
                status="warning"
                title="当前控件暂未支持"
                subTitle={`${spatialCtrl.tag} (${spatialCtrl.type}) 对 ${tag ?? '未知'} 类型暂未实现`}
              />
            )
          })}
          {!currentTask && taskLoading && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}><Spin /></div>
          )}
        </div>

        {/* Side Panel: Classification Controls */}
        <div style={{
          width: 280, borderLeft: '1px solid var(--ant-color-border)',
          overflowY: 'auto', padding: 12, display: 'flex', flexDirection: 'column', gap: 12,
        }}>
          {/* Per-Region Controls */}
          {perRegionControls.map((ctrl) => {
            const objCfg = objectMap.get(ctrl.toName)
            const imgUrl = objCfg ? (currentTask.data?.[objCfg.field] as string | undefined) : undefined
            const selRegion = regionsHook.selectedRegionId
              ? regionsHook.regions.find((r) => r.id === regionsHook.selectedRegionId) ?? null
              : null
            return (
            <Card
              key={ctrl.name}
              size="small"
              title={
                <Space>
                  <span>{ctrl.tag}</span>
                  {regionsHook.selectedRegionId
                    ? <Tag color="blue">已选中区域</Tag>
                    : <Tag color="default">等待选择</Tag>
                  }
                </Space>
              }
            >
              {renderClassificationControl(
                ctrl, currentTask, objCfg, readOnly,
                true, regionsHook.selectedRegionId,
                regionsHook.selectedRegionId
                  ? regionsHook.getRegionResult(regionsHook.selectedRegionId, ctrl.name)
                  : null,
                handlePerRegionResult(ctrl.name),
                undefined,
                submitMutation.isPending,
                selRegion,
                regionsHook.imageDimensions,
                imgUrl,
              )}
            </Card>
            )
          })}

          {/* Divider */}
          {perRegionControls.length > 0 && globalClassificationControls.length > 0 && (
            <Divider style={{ margin: '4px 0' }}>全局标注</Divider>
          )}

          {/* Global Classification Controls */}
          {globalClassificationControls.map((ctrl) => (
            <Card key={ctrl.name} size="small" title={ctrl.tag}>
              {renderClassificationControl(
                ctrl, currentTask, objectMap.get(ctrl.toName), readOnly,
                false, null, null, undefined, handleGlobalResult(ctrl.name),
                submitMutation.isPending,
                null, null, undefined,
              )}
            </Card>
          ))}

          {/* Relation Controls */}
          {relationControls.length > 0 && (
            <>
              <Divider style={{ margin: '4px 0' }}>关系标注</Divider>
              {relationControls.map((relCtrl) => (
                <Card key={relCtrl.name} size="small" title={relCtrl.tag}>
                  {!readOnly && (
                    <Space direction="vertical" style={{ width: '100%' }} size="small">
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        点击左侧区域列表中的一个区域作为源，再点击另一个作为目标来创建关系。
                      </Typography.Text>
                      {relCtrl.choices.length > 0 && !relationsHook.selectedRelationId && (
                        <Space wrap>
                          {relCtrl.choices.map((ch) => (
                            <Tag
                              key={ch.value}
                              color="blue"
                              style={{ cursor: 'pointer' }}
                              onClick={() => {
                                // Start relation creation: select source region first
                                if (regionsHook.selectedRegionId) {
                                  relationsHook.addRelation({
                                    id: crypto.randomUUID(),
                                    fromRegionId: regionsHook.selectedRegionId,
                                    toRegionId: '', // will be set on second click
                                    label: ch.value,
                                    sourceControlName: relCtrl.name,
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
                      {relationsHook.relations.filter((r) => r.sourceControlName === relCtrl.name).map((rel, i) => {
                        const fromRegion = regionsHook.regions.find((r) => r.id === rel.fromRegionId)
                        const toRegion = regionsHook.regions.find((r) => r.id === rel.toRegionId)
                        return (
                          <div key={rel.id} style={{ display: 'flex', alignItems: 'center', gap: 4, marginBottom: 4 }}>
                            <Tag color="blue">{rel.label || `关系${i + 1}`}</Tag>
                            <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                              {fromRegion?.label || `区域`} → {toRegion?.label || `区域`}
                            </Typography.Text>
                            {!readOnly && (
                              <Button
                                type="text" size="small" danger
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
              ))}
            </>
          )}

          {/* Submit */}
          {!readOnly && (
            <Button
              type="primary" size="large" block
              onClick={handleSubmit} loading={submitMutation.isPending}
              disabled={regionsHook.regions.length === 0
                && Object.values(globalResults).every((a) => a.length === 0)}
            >
              提交标注 ({regionsHook.regions.length})
            </Button>
          )}
        </div>

        {/* Guidelines */}
        <AnnotationGuideline
          project={project}
          labels={parsedConfig?.controls.flatMap((c) => c.choices.map((ch) => ch.value)) ?? []}
          collapsed={guidelineCollapsed}
          onToggle={() => setGuidelineCollapsed(!guidelineCollapsed)}
        />
      </div>

      {/* Region List — integrated into each annotator's overlay */}

      <Modal open={hotkeyHelpOpen} title="快捷键" footer={null} onCancel={() => setHotkeyHelpOpen(false)}>
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

// ── Classification-Only Workspace (no spatial controls) ─────────────────────

function ClassificationOnlyWorkspace({
  task, project, objectConfig, controls,
  onSubmit, submitting, readOnly,
  guidelineCollapsed, onToggleGuideline, onBack,
  currentTaskIndex, totalTasks, completedTasks, onPrev, onNext, onHotkeyHelp,
  renderControl,
}: {
  task: AnnotationTask
  project: NonNullable<ReturnType<typeof useQuery>['data']>
  objectConfig?: LabelStudioObjectConfig
  controls: LabelStudioControlConfig[]
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
  renderControl: (ctrl: LabelStudioControlConfig) => ReactNode
}) {
  const objectValue = objectConfig
    ? (task.data?.[objectConfig.field] as string | undefined)
    : undefined

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        padding: '8px 16px', borderBottom: '1px solid var(--ant-color-border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={onBack}>返回</Button>
          <span style={{ fontWeight: 500 }}>{(project as { name: string }).name}</span>
          {readOnly && <Tag color="green">已完成 - 只读</Tag>}
        </div>
        <Space>
          <TaskNavigator
            currentTaskIndex={currentTaskIndex} totalTasks={totalTasks}
            completedTasks={completedTasks} onPrev={onPrev} onNext={onNext}
            hasPrev={currentTaskIndex > 0} hasNext={true}
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
          {objectConfig?.tag === 'Image' && objectValue ? (
            <div style={{ textAlign: 'center', marginBottom: 16 }}>
              <img src={appendAuthToken(objectValue)} style={{ maxHeight: 400, maxWidth: '100%' }} alt="" />
            </div>
          ) : (objectConfig?.tag === 'Text' || objectConfig?.tag === 'HyperText') ? (
            <Card size="small" style={{ marginBottom: 16 }}>
              <Typography.Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
                {objectValue || '无内容'}
              </Typography.Paragraph>
            </Card>
          ) : null}
          {controls.map((ctrl) => (
            <div key={ctrl.name} style={{ marginBottom: 16 }}>
              {renderControl(ctrl)}
            </div>
          ))}
          {!readOnly && (
            <Button type="primary" onClick={onSubmit} loading={submitting} block>
              提交标注
            </Button>
          )}
        </div>
        <AnnotationGuideline
          project={project}
          labels={controls.flatMap((c) => c.choices.map((ch) => ch.value))}
          collapsed={guidelineCollapsed}
          onToggle={onToggleGuideline}
        />
      </div>
    </div>
  )
}
