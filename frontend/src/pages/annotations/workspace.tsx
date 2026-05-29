import { useState, useCallback, useEffect, type ComponentType } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button, Result, Spin } from 'antd'
import { ArrowLeftOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  getAnnotationProjectDetail,
  getNextAnnotationTask,
  startAnnotation,
  submitAnnotation,
} from '@/services/annotations'
import { getMessageInstance } from '@/utils/messageHolder'
import type {
  AnnotationTask,
  AnnotationProjectDetail,
  AnnotationResultItem,
} from '@/types/annotation'
import { parseLabelConfig } from './utils/parseLabelConfig'
import AnnotationGuideline from './components/AnnotationGuideline'
import TaskNavigator from './components/TaskNavigator'
import ObjectDetectionAnnotator from './components/ObjectDetectionAnnotator'
import ImageSegmentationAnnotator from './components/ImageSegmentationAnnotator'
import TextAreaAnnotator from './components/TextAreaAnnotator'
import ChoicesAnnotator from './components/ChoicesAnnotator'
import type { LabelStudioControlConfig, LabelStudioObjectConfig } from './utils/parseLabelConfig'

interface AnnotatorProps {
  task: AnnotationTask
  project: AnnotationProjectDetail
  labels: string[]
  objectConfig?: LabelStudioObjectConfig
  controlConfig?: LabelStudioControlConfig
  onSubmit: (result: AnnotationResultItem[]) => void
  submitting: boolean
}

function getAnnotatorComponent(
  control: LabelStudioControlConfig | undefined,
  object: LabelStudioObjectConfig | undefined,
): ComponentType<AnnotatorProps> | null {
  if (!control || !object) return null
  if (control.type === 'choices') return ChoicesAnnotator
  if (control.type === 'rectanglelabels' && object.tag === 'Image') return ObjectDetectionAnnotator
  if (control.type === 'polygonlabels' && object.tag === 'Image') return ImageSegmentationAnnotator
  if (control.type === 'textarea') return TextAreaAnnotator
  return null
}

export default function AnnotationWorkspacePage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [currentTask, setCurrentTask] = useState<AnnotationTask | null>(null)
  const [taskIndex, setTaskIndex] = useState(0)
  const [guidelineCollapsed, setGuidelineCollapsed] = useState(false)
  const [initialized, setInitialized] = useState(false)
  const [taskLoading, setTaskLoading] = useState(false)
  const [taskLoadFailed, setTaskLoadFailed] = useState(false)

  const { data: project, isLoading: projectLoading } = useQuery({
    queryKey: ['annotationProject', projectId],
    queryFn: () => getAnnotationProjectDetail(projectId!),
    enabled: !!projectId,
  })

  const parsedConfig = project ? parseLabelConfig(project.labelConfig) : null
  const primaryControl = parsedConfig?.controls[0]
  const primaryObject = parsedConfig?.objects.find(
    (object) => object.name === primaryControl?.toName,
  )
  const labels = parsedConfig?.labels ?? []

  const loadNextTask = useCallback(async () => {
    if (!projectId) return
    setTaskLoading(true)
    setTaskLoadFailed(false)
    try {
      const task = await getNextAnnotationTask(projectId)
      if (task) {
        const readyTask = task.status === 'in_progress' ? task : await startAnnotation(task.id)
        setCurrentTask(readyTask)
        setTaskIndex((prev) => prev + 1)
      } else {
        setCurrentTask(null)
      }
    } catch {
      setCurrentTask(null)
      setTaskLoadFailed(true)
      getMessageInstance()?.error('加载标注任务失败')
    } finally {
      setTaskLoading(false)
    }
  }, [projectId])

  const submitMutation = useMutation({
    mutationFn: ({ taskId, result }: { taskId: string; result: AnnotationResultItem[] }) =>
      submitAnnotation(taskId, { result }),
    onSuccess: () => {
      getMessageInstance()?.success('标注提交成功')
      queryClient.invalidateQueries({ queryKey: ['annotationProject', projectId] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTasks'] })
      queryClient.invalidateQueries({ queryKey: ['myAnnotationTaskSummary'] })
      loadNextTask()
    },
  })

  useEffect(() => {
    if (project && !initialized) {
      setInitialized(true)
      loadNextTask()
    }
  }, [project, initialized, loadNextTask])

  const handleSubmit = useCallback(
    (result: AnnotationResultItem[]) => {
      if (!currentTask) return
      submitMutation.mutate({ taskId: currentTask.id, result })
    },
    [currentTask, submitMutation],
  )

  if (projectLoading || !project) {
    return (
      <div
        style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}
      >
        <Spin tip="加载中...">
          <div />
        </Spin>
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
            <Button type="primary" onClick={loadNextTask}>
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
          subTitle="该项目中的所有标注任务已完成"
          extra={
            <Button type="primary" onClick={() => navigate('/annotations')}>
              返回标注列表
            </Button>
          }
        />
      </div>
    )
  }

  const AnnotatorComponent = getAnnotatorComponent(primaryControl, primaryObject)
  const totalTasks = project.totalTasks || 0
  const completedTasks = project.completedTasks || 0

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
          <Button type="text" icon={<ArrowLeftOutlined />} onClick={() => navigate('/annotations')}>
            返回
          </Button>
          <span style={{ fontWeight: 500 }}>{project.name}</span>
        </div>
        <TaskNavigator
          currentTaskIndex={taskIndex}
          totalTasks={totalTasks}
          completedTasks={completedTasks}
          onPrev={() => {}}
          onNext={() => {}}
          hasPrev={false}
          hasNext={!!currentTask}
        />
        <Button type="text" onClick={() => setGuidelineCollapsed(!guidelineCollapsed)}>
          规范 {guidelineCollapsed ? '▸' : '▾'}
        </Button>
      </div>

      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        <div style={{ flex: 1, padding: 16, overflowY: 'auto' }}>
          {currentTask && AnnotatorComponent && (
            <AnnotatorComponent
              task={currentTask}
              project={project}
              labels={labels}
              objectConfig={primaryObject}
              controlConfig={primaryControl}
              onSubmit={handleSubmit}
              submitting={submitMutation.isPending}
            />
          )}
          {currentTask && !AnnotatorComponent && (
            <Result
              status="warning"
              title="当前标注配置暂未支持"
              subTitle="该 Label Studio XML 控件还没有对应的 KubeAI 自研标注组件。"
            />
          )}
          {!currentTask && taskLoading && (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 48 }}>
              <Spin tip="加载任务中...">
                <div />
              </Spin>
            </div>
          )}
        </div>

        <AnnotationGuideline
          project={project}
          labels={labels}
          collapsed={guidelineCollapsed}
          onToggle={() => setGuidelineCollapsed(!guidelineCollapsed)}
        />
      </div>
    </div>
  )
}
